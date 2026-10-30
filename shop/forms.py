import re
from uuid import uuid4

from django import forms
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone

from .models import (
    GUEST_PREFIX, Appointment, AppointmentService, ContactMessage, Customer, Service, Vehicle,
)


def normalize_phone(raw):
    """Accept common US formats and return 555-123-4567, or raise ValidationError."""
    raw = (raw or "").strip()
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if not re.fullmatch(r"[\d\s().+-]+", raw) or len(digits) != 10:
        raise forms.ValidationError("Enter a 10-digit phone number, like 555-123-4567.")
    return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"


class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ["name", "email", "message"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "message": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
        }


class RegisterForm(forms.ModelForm):
    password = forms.CharField(
        min_length=8, widget=forms.PasswordInput(attrs={"class": "form-control"}),
        help_text="At least 8 characters.",
    )
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-control"}))

    class Meta:
        model = Customer
        fields = ["name", "phone", "email", "username"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "username": forms.TextInput(attrs={"class": "form-control"}),
        }

    def clean_phone(self):
        return normalize_phone(self.cleaned_data["phone"])

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if username.lower().startswith(GUEST_PREFIX):
            raise forms.ValidationError(f'Usernames cannot start with "{GUEST_PREFIX}".')
        return username

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password") and cleaned.get("password") != cleaned.get("confirm_password"):
            self.add_error("confirm_password", "Passwords do not match.")
        return cleaned

    def save(self, commit=True):
        customer = super().save(commit=False)
        customer.password_hash = make_password(self.cleaned_data["password"])
        if commit:
            customer.save()
        return customer


class LoginForm(forms.Form):
    username = forms.CharField(max_length=50, widget=forms.TextInput(attrs={"class": "form-control"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-control"}))


class ServiceChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.name} - ${obj.price}"


class BookingForm(forms.Form):
    """Appointment request. Guests give contact info; logged-in customers use their account."""

    name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={"class": "form-control"}))
    phone = forms.CharField(max_length=20, widget=forms.TextInput(attrs={"class": "form-control"}))
    email = forms.EmailField(max_length=255, widget=forms.EmailInput(attrs={"class": "form-control"}))

    vehicle = forms.ModelChoiceField(
        queryset=Vehicle.objects.none(), required=False, empty_label="Add a new vehicle",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    make = forms.CharField(max_length=50, required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    model = forms.CharField(max_length=50, required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    year = forms.IntegerField(required=False, min_value=1900, widget=forms.NumberInput(attrs={"class": "form-control"}))
    plate = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={"class": "form-control"}))

    services = ServiceChoiceField(
        queryset=Service.objects.order_by("name"),
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        error_messages={"required": "Choose at least one service."},
    )
    date = forms.DateField(widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date", "class": "form-control"}))
    time = forms.TimeField(widget=forms.TimeInput(format="%H:%M", attrs={"type": "time", "class": "form-control"}))

    def __init__(self, *args, customer=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.customer = customer
        self.fields["date"].widget.attrs["min"] = timezone.localdate().isoformat()
        if customer:
            for field in ("name", "phone", "email"):
                del self.fields[field]
            vehicles = customer.vehicles.order_by("year", "make", "model")
            if vehicles.exists():
                self.fields["vehicle"].queryset = vehicles
            else:
                del self.fields["vehicle"]
        else:
            del self.fields["vehicle"]

    def clean_phone(self):
        return normalize_phone(self.cleaned_data["phone"])

    def clean_year(self):
        year = self.cleaned_data.get("year")
        if year and year > timezone.localdate().year + 1:
            raise forms.ValidationError("Enter a valid model year.")
        return year

    def clean_plate(self):
        plate = re.sub(r"[\s-]", "", (self.cleaned_data.get("plate") or "").upper())
        if plate and not re.fullmatch(r"[A-Z0-9]{1,20}", plate):
            raise forms.ValidationError("Plates can only use letters, numbers, spaces, and dashes.")
        return plate

    def clean_date(self):
        day = self.cleaned_data["date"]
        today = timezone.localdate()
        if day < today:
            raise forms.ValidationError("Choose today or a future date.")
        if (day - today).days > 365:
            raise forms.ValidationError("Choose a date within the next year.")
        return day

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("vehicle"):
            for name in ("make", "model", "year", "plate"):
                if not cleaned.get(name) and name not in self.errors:
                    self.add_error(name, "This field is required.")
        for name in ("make", "model"):
            if cleaned.get(name):
                cleaned[name] = cleaned[name].strip()
        return cleaned

    def _guest_customer(self):
        cd = self.cleaned_data
        guest = Customer.objects.filter(phone=cd["phone"], username__startswith=GUEST_PREFIX).first()
        if guest:  # repeat guest: reuse the record, keep contact info current
            guest.name, guest.email = cd["name"], cd["email"]
            guest.save(update_fields=["name", "email"])
            return guest
        return Customer.objects.create(
            name=cd["name"], phone=cd["phone"], email=cd["email"],
            username=f"{GUEST_PREFIX}{uuid4().hex[:16]}",
            password_hash=make_password(None),  # unusable: guests can never log in
        )

    @transaction.atomic
    def book(self):
        cd = self.cleaned_data
        customer = self.customer or self._guest_customer()
        vehicle = cd.get("vehicle")
        if vehicle is None:
            vehicle, _ = Vehicle.objects.get_or_create(
                customer=customer, plate=cd["plate"],
                defaults={"make": cd["make"], "model": cd["model"], "year": cd["year"]},
            )
        appointment = Appointment.objects.create(vehicle=vehicle, date=cd["date"], time=cd["time"])
        for service in cd["services"]:
            AppointmentService.objects.create(appointment=appointment, service=service)
        return appointment
