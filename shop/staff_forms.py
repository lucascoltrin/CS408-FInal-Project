from django import forms
from django.forms import modelformset_factory
from django.utils import timezone

from .models import Appointment, AppointmentService, Service

SERVICE_STATUS_CHOICES = [("pending", "Pending"), ("in_progress", "In progress"), ("completed", "Completed")]


class AppointmentStaffForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ["status", "date", "time"]
        widgets = {
            "status": forms.Select(attrs={"class": "form-select"}),
            "date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date", "class": "form-control"}),
            "time": forms.TimeInput(format="%H:%M", attrs={"type": "time", "class": "form-control"}),
        }


class ServiceRowForm(forms.ModelForm):
    """One service on an appointment: its progress, the labor, and what it cost."""

    status = forms.ChoiceField(choices=SERVICE_STATUS_CHOICES, widget=forms.Select(attrs={"class": "form-select form-select-sm"}))
    hours = forms.DecimalField(
        required=False, min_value=0, max_digits=5, decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.25", "min": "0"}),
    )
    cost = forms.DecimalField(
        required=False, min_value=0, max_digits=10, decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.01", "min": "0"}),
    )

    class Meta:
        model = AppointmentService
        fields = ["status", "hours", "cost", "date_completed"]
        widgets = {
            "date_completed": forms.DateInput(
                format="%Y-%m-%d", attrs={"type": "date", "class": "form-control form-control-sm"},
            ),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("status") == "completed" and not cleaned.get("date_completed"):
            cleaned["date_completed"] = timezone.localdate()  # completed today unless the owner says otherwise
        return cleaned


ServiceRowFormSet = modelformset_factory(AppointmentService, form=ServiceRowForm, extra=0, can_delete=True)


class AddServiceForm(forms.Form):
    """Add extra work found during the job, from the services catalog."""

    service = forms.ModelChoiceField(
        queryset=Service.objects.none(), required=False, empty_label="Add a service...",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, appointment, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["service"].queryset = (
            Service.objects.exclude(appointment_services__appointment=appointment).order_by("name")
        )
