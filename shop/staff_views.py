from functools import wraps

from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.db.models import Count
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import LoginForm
from .models import Appointment, AppointmentService, Employee
from .staff_forms import AddServiceForm, AppointmentStaffForm, ServiceRowFormSet
from .views import _safe_next

_DUMMY_HASH = make_password("not-a-real-password")


def _current_employee(request):
    employee_id = request.session.get("employee_id")
    return Employee.objects.filter(pk=employee_id).first() if employee_id else None


def staff_required(view):
    """Only a logged-in employee gets through. Customer logins do not count."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if _current_employee(request) is None:
            request.session.pop("employee_id", None)
            target = request.get_full_path() if request.method == "GET" else reverse("dashboard")
            return redirect(f"{reverse('staff_login')}?next={target}")
        return view(request, *args, **kwargs)
    return wrapper


def staff_login(request):
    if _current_employee(request):
        return redirect("dashboard")
    error = None
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            employee = Employee.objects.filter(username=form.cleaned_data["username"]).first()
            ok = check_password(form.cleaned_data["password"], employee.password_hash if employee else _DUMMY_HASH)
            if employee and ok:
                request.session.cycle_key()
                request.session["employee_id"] = employee.pk
                return redirect(_safe_next(request, "dashboard"))
            error = "Invalid username or password."
    else:
        form = LoginForm()
    return render(request, "shop/staff_login.html", {"form": form, "error": error, "next": request.GET.get("next", "")})


@require_POST
def staff_logout(request):
    request.session.flush()
    return redirect("home")


STATUS_ORDER = [key for key, _ in Appointment.STATUS_CHOICES]


@staff_required
def dashboard(request):
    status = request.GET.get("status", "")
    appointments = Appointment.objects.select_related("vehicle__customer").prefetch_related("appointment_services__service")
    if status in STATUS_ORDER:
        appointments = appointments.filter(status=status)
    else:
        status = ""

    # Upcoming first (soonest at the top), then past appointments (most recent first).
    today = timezone.localdate()
    rows = list(appointments)
    upcoming = sorted((a for a in rows if a.date >= today), key=lambda a: (a.date, a.time))
    past = sorted((a for a in rows if a.date < today), key=lambda a: (a.date, a.time), reverse=True)

    counts = dict(Appointment.objects.values_list("status").annotate(n=Count("id")))
    tabs = [("", "All", sum(counts.values()))] + [
        (key, label, counts.get(key, 0)) for key, label in Appointment.STATUS_CHOICES
    ]
    return render(request, "shop/dashboard.html", {
        "appointments": upcoming + past, "tabs": tabs, "active_status": status,
    })


@staff_required
@require_POST
def dashboard_action(request, pk):
    """Quick approve / deny from the list."""
    appointment = get_object_or_404(Appointment, pk=pk)
    new_status = {"approve": "approved", "deny": "denied"}.get(request.POST.get("action"))
    if new_status is None:
        return HttpResponseBadRequest("Unknown action.")
    appointment.status = new_status
    appointment.save(update_fields=["status"])
    messages.success(request, f"Appointment for {appointment.vehicle.plate} marked {appointment.get_status_display().lower()}.")
    return redirect(_safe_next(request, "dashboard"))


@staff_required
def dashboard_appointment(request, pk):
    appointment = get_object_or_404(
        Appointment.objects.select_related("vehicle__customer"), pk=pk,
    )
    rows = appointment.appointment_services.select_related("service").order_by("id")
    if request.method == "POST":
        form = AppointmentStaffForm(request.POST, instance=appointment)
        formset = ServiceRowFormSet(request.POST, queryset=rows, prefix="services")
        add_form = AddServiceForm(request.POST, appointment=appointment, prefix="add")
        valid = [form.is_valid(), formset.is_valid(), add_form.is_valid()]
        if all(valid):
            with transaction.atomic():
                form.save()
                formset.save()
                extra = add_form.cleaned_data.get("service")
                if extra:
                    AppointmentService.objects.create(appointment=appointment, service=extra)
            messages.success(request, "Appointment saved.")
            return redirect("dashboard_appointment", pk=appointment.pk)
    else:
        form = AppointmentStaffForm(instance=appointment)
        formset = ServiceRowFormSet(queryset=rows, prefix="services")
        add_form = AddServiceForm(appointment=appointment, prefix="add")
    return render(request, "shop/dashboard_appointment.html", {
        "appointment": appointment, "customer": appointment.vehicle.customer,
        "form": form, "formset": formset, "add_form": add_form,
    })


@staff_required
def dashboard_delete(request, pk):
    appointment = get_object_or_404(Appointment.objects.select_related("vehicle__customer"), pk=pk)
    if request.method == "POST":
        label = f"{appointment.vehicle.plate} on {appointment.date}"
        appointment.delete()  # also removes its service rows, parts, and invoices
        messages.success(request, f"Deleted the appointment for {label}.")
        return redirect("dashboard")
    return render(request, "shop/dashboard_delete.html", {"appointment": appointment})
