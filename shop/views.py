from decimal import Decimal
from functools import wraps

from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import (
    AppointmentEditForm, BookingForm, ContactForm, LoginForm, RegisterForm, VehicleLookupForm,
)
from .models import Appointment, Customer, Service

# Used to spend the same time hashing when a username does not exist.
_DUMMY_HASH = make_password("not-a-real-password")


def _safe_next(request, default="home"):
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return target
    return reverse(default)


def customer_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.session.get("customer_id"):
            messages.info(request, "Please log in first.")
            target = request.path if request.method == "GET" else reverse("services")
            return redirect(f"{reverse('login')}?next={target}")
        return view(request, *args, **kwargs)
    return wrapper


def _log_in(request, customer):
    request.session.cycle_key()
    request.session["customer_id"] = customer.pk


def home(request):
    return render(request, "shop/home.html")


def about(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect(f"{reverse('about')}?sent=1")
    else:
        form = ContactForm()
    return render(request, "shop/about.html", {"form": form, "sent": request.GET.get("sent") == "1"})


def services(request):
    cart = request.session.get("cart", []) if request.session.get("customer_id") else []
    return render(request, "shop/services.html", {
        "services": Service.objects.order_by("name"),
        "cart": cart,
    })


def register(request):
    if request.session.get("customer_id"):
        return redirect("home")
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            customer = form.save()
            _log_in(request, customer)
            messages.success(request, f"Welcome, {customer.name}! Your account was created.")
            return redirect(_safe_next(request, "services"))
    else:
        form = RegisterForm()
    return render(request, "shop/register.html", {"form": form, "next": request.GET.get("next", "")})


def login_view(request):
    if request.session.get("customer_id"):
        return redirect("home")
    error = None
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            customer = Customer.objects.filter(username=form.cleaned_data["username"]).first()
            password = form.cleaned_data["password"]
            ok = check_password(password, customer.password_hash if customer else _DUMMY_HASH)
            if customer and ok:
                _log_in(request, customer)
                messages.success(request, f"Welcome back, {customer.name}.")
                return redirect(_safe_next(request, "services"))
            error = "Invalid username or password."
    else:
        form = LoginForm()
    return render(request, "shop/login.html", {"form": form, "error": error, "next": request.GET.get("next", "")})


@require_POST
def logout_view(request):
    request.session.flush()  # also clears the cart
    return redirect("home")


def _cart_services(request):
    ids = request.session.get("cart", [])
    found = {s.pk: s for s in Service.objects.filter(pk__in=ids)}
    return [found[i] for i in ids if i in found]


@customer_required
def cart(request):
    items = _cart_services(request)
    total = sum((s.price for s in items), Decimal("0.00"))
    return render(request, "shop/cart.html", {"items": items, "total": total})


@customer_required
@require_POST
def cart_add(request):
    service = get_object_or_404(Service, pk=request.POST.get("service_id"))
    cart = request.session.get("cart", [])
    if service.pk in cart:
        messages.info(request, f"{service.name} is already in your cart.")
    else:
        cart.append(service.pk)
        request.session["cart"] = cart
        messages.success(request, f"Added {service.name} to your cart.")
    return redirect(_safe_next(request, "services"))


@customer_required
@require_POST
def cart_remove(request):
    try:
        service_id = int(request.POST.get("service_id", ""))
    except ValueError:
        return redirect("cart")
    request.session["cart"] = [i for i in request.session.get("cart", []) if i != service_id]
    messages.info(request, "Removed from your cart.")
    return redirect("cart")


def _current_customer(request):
    customer_id = request.session.get("customer_id")
    return Customer.objects.filter(pk=customer_id).first() if customer_id else None


def book(request):
    customer = _current_customer(request)
    if request.method == "POST":
        form = BookingForm(request.POST, customer=customer)
        if form.is_valid():
            appointment = form.book()
            if customer:
                request.session["cart"] = []
            request.session["last_appointment_id"] = appointment.pk
            return redirect("book_confirmation")
    else:
        initial = {"services": request.session.get("cart", [])} if customer else {}
        form = BookingForm(customer=customer, initial=initial)
    return render(request, "shop/book.html", {"form": form})


def book_confirmation(request):
    """Shows the visitor's most recent booking. Tied to the session, so IDs are never in the URL."""
    appointment_id = request.session.get("last_appointment_id")
    appointment = (
        Appointment.objects.select_related("vehicle__customer")
        .prefetch_related("appointment_services__service")
        .filter(pk=appointment_id).first()
        if appointment_id else None
    )
    if appointment is None:
        return redirect("book")
    items = [row.service for row in appointment.appointment_services.all()]
    total = sum((s.price for s in items), Decimal("0.00"))
    return render(request, "shop/book_confirmation.html", {
        "appointment": appointment, "items": items, "total": total,
    })


def _with_history(vehicles):
    """Attach each vehicle's appointments (newest first) and their services in a few queries."""
    appointments = Appointment.objects.order_by("-date", "-time").prefetch_related("appointment_services__service")
    return vehicles.prefetch_related(Prefetch("appointments", queryset=appointments))


def history(request):
    """Service history. Logged-in customers see their own vehicles; guests look one up by plate + phone."""
    customer = _current_customer(request)
    lookup_results = None
    if request.method == "POST":
        lookup_form = VehicleLookupForm(request.POST)
        if lookup_form.is_valid():
            lookup_results = list(_with_history(lookup_form.find_vehicles()))
    else:
        lookup_form = VehicleLookupForm()
    own_vehicles = list(_with_history(customer.vehicles.order_by("year", "make", "model"))) if customer else None
    return render(request, "shop/history.html", {
        "own_vehicles": own_vehicles, "lookup_form": lookup_form, "lookup_results": lookup_results,
    })


@customer_required
def appointment_edit(request, pk):
    # Scoped to the logged-in customer, so other people's appointments are a plain 404.
    appointment = get_object_or_404(
        Appointment.objects.select_related("vehicle"), pk=pk, vehicle__customer_id=request.session["customer_id"],
    )
    if not appointment.can_edit:
        messages.info(request, "That appointment can no longer be changed online.")
        return redirect("history")
    if request.method == "POST":
        form = AppointmentEditForm(request.POST)
        if form.is_valid():
            was_approved = appointment.status == "approved"
            form.save(appointment)
            messages.success(
                request,
                "Appointment updated. It is pending until the owner approves it again."
                if was_approved else "Appointment updated.",
            )
            return redirect("history")
    else:
        form = AppointmentEditForm(initial={
            "date": appointment.date, "time": appointment.time,
            "services": list(appointment.appointment_services.values_list("service_id", flat=True)),
        })
    return render(request, "shop/appointment_edit.html", {"form": form, "appointment": appointment})
