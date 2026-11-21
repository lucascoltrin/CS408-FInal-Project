import re
from uuid import uuid4

from django import forms
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone

from .models import (
    GUEST_PREFIX, Appointment, AppointmentService, ContactMessage, Customer, PartUsed, Review, Service, Vehicle,
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


def normalize_plate(raw):
    """Uppercase and strip spaces/dashes so 'abc 123' and 'ABC-123' match. Blank stays blank."""
    plate = re.sub(r"[\s-]", "", (raw or "").upper())
    if plate and not re.fullmatch(r"[A-Z0-9]{1,20}", plate):
        raise forms.ValidationError("Plates can only use letters, numbers, spaces, and dashes.")
    return plate


def validate_booking_date(day):
    today = timezone.localdate()
    if day < today:
        raise forms.ValidationError("Choose today or a future date.")
    if (day - today).days > 365:
        raise forms.ValidationError("Choose a date within the next year.")
    return day


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
        return normalize_plate(self.cleaned_data.get("plate"))

    def clean_date(self):
        return validate_booking_date(self.cleaned_data["date"])

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


class VehicleLookupForm(forms.Form):
    """Guest lookup. Both the plate and the phone used at booking must match."""

    plate = forms.CharField(max_length=20, widget=forms.TextInput(attrs={"class": "form-control"}))
    phone = forms.CharField(
        max_length=20, label="Phone number used when booking",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    def clean_plate(self):
        plate = normalize_plate(self.cleaned_data["plate"])
        if not plate:
            raise forms.ValidationError("Enter a license plate.")
        return plate

    def clean_phone(self):
        return normalize_phone(self.cleaned_data["phone"])

    def find_vehicles(self):
        cd = self.cleaned_data
        return Vehicle.objects.filter(plate=cd["plate"], customer__phone=cd["phone"])


class AppointmentEditForm(forms.Form):
    """Lets a customer change the date, time, and services of an upcoming appointment."""

    services = ServiceChoiceField(
        queryset=Service.objects.order_by("name"),
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        error_messages={"required": "Choose at least one service."},
    )
    date = forms.DateField(widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date", "class": "form-control"}))
    time = forms.TimeField(widget=forms.TimeInput(format="%H:%M", attrs={"type": "time", "class": "form-control"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date"].widget.attrs["min"] = timezone.localdate().isoformat()

    def clean_date(self):
        return validate_booking_date(self.cleaned_data["date"])

    @transaction.atomic
    def save(self, appointment):
        cd = self.cleaned_data
        appointment.date, appointment.time = cd["date"], cd["time"]
        appointment.status = "pending"  # any change needs the owner's approval again
        appointment.save(update_fields=["date", "time", "status"])
        wanted = {service.pk for service in cd["services"]}
        appointment.appointment_services.exclude(service_id__in=wanted).delete()
        have = set(appointment.appointment_services.values_list("service_id", flat=True))
        for service in cd["services"]:
            if service.pk not in have:
                AppointmentService.objects.create(appointment=appointment, service=service)
        return appointment


class ReviewForm(forms.ModelForm):
    rating = forms.TypedChoiceField(
        coerce=int, choices=[(5, "5 - Excellent"), (4, "4 - Good"), (3, "3 - Okay"), (2, "2 - Poor"), (1, "1 - Terrible")],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    comment = forms.CharField(
        max_length=1000, widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}),
    )

    class Meta:
        model = Review
        fields = ["rating", "comment"]

    def clean_comment(self):
        comment = self.cleaned_data["comment"].strip()
        if not comment:
            raise forms.ValidationError("Write a few words about your visit.")
        return comment


class ServiceRowChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.service.name


class PartUsedForm(forms.ModelForm):
    """Staff enter parts by hand, since parts are supplied by the customer or mechanic."""

    appointment_service = ServiceRowChoiceField(
        queryset=AppointmentService.objects.none(), label="Service",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    name = forms.CharField(max_length=100, label="Part", widget=forms.TextInput(attrs={"class": "form-control"}))
    quantity = forms.IntegerField(
        min_value=1, max_value=999, initial=1, widget=forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
    )
    price = forms.DecimalField(
        min_value=0, max_digits=10, decimal_places=2, label="Price each ($)",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
    )

    class Meta:
        model = PartUsed
        fields = ["appointment_service", "name", "quantity", "price"]

    def __init__(self, *args, appointment, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["appointment_service"].queryset = (
            appointment.appointment_services.select_related("service").order_by("id")
        )
