from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


GUEST_PREFIX = "guest-"  # usernames starting with this belong to one-off guest bookings


class Customer(models.Model):
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    email = models.EmailField(max_length=255)
    username = models.CharField(max_length=50, unique=True)
    password_hash = models.CharField(max_length=255)

    class Meta:
        db_table = "customers"

    @property
    def is_guest(self):
        return self.username.startswith(GUEST_PREFIX)

    @property
    def display_name(self):
        """First name plus last initial, so reviews do not show full names."""
        parts = self.name.split()
        if not parts:
            return "Customer"
        return parts[0] if len(parts) == 1 else f"{parts[0]} {parts[-1][0].upper()}."

    def reviewable_appointments(self):
        """Visits that count toward a review: completed, or accepted and already in the past."""
        today = timezone.localdate()
        return Appointment.objects.filter(vehicle__customer=self).filter(
            models.Q(status="completed")
            | models.Q(status__in=["approved", "in_progress"], date__lt=today)
        )

    def reviews_remaining(self):
        """One review per qualifying visit."""
        return max(self.reviewable_appointments().count() - self.reviews.count(), 0)

    def __str__(self):
        return self.name


class Vehicle(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="vehicles")
    make = models.CharField(max_length=50)
    model = models.CharField(max_length=50)
    year = models.PositiveIntegerField()
    plate = models.CharField(max_length=20)

    class Meta:
        db_table = "vehicles"
        constraints = [
            models.UniqueConstraint(fields=["customer", "plate"], name="unique_plate_per_customer"),
        ]

    def __str__(self):
        return f"{self.year} {self.make} {self.model} ({self.plate})"


class Service(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = "services"

    def __str__(self):
        return self.name


class Appointment(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("denied", "Denied"),
        ("in_progress", "In progress"),
        ("completed", "Completed"),
    ]
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="appointments")
    date = models.DateField()
    time = models.TimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    class Meta:
        db_table = "appointments"

    BADGE_COLORS = {
        "pending": "warning", "approved": "primary", "in_progress": "info",
        "completed": "success", "denied": "danger",
    }

    @property
    def status_badge(self):
        return self.BADGE_COLORS.get(self.status, "secondary")

    @property
    def can_edit(self):
        """Customers may change an appointment only while it is upcoming and not yet started."""
        return self.status in ("pending", "approved") and self.date >= timezone.localdate()

    def __str__(self):
        return f"{self.vehicle} on {self.date}"


class AppointmentService(models.Model):
    """Join table: one row per service selected for an appointment."""
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name="appointment_services")
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="appointment_services")
    status = models.CharField(max_length=20, default="pending")
    hours = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    date_completed = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "appointment_services"


class PartUsed(models.Model):
    appointment_service = models.ForeignKey(AppointmentService, on_delete=models.CASCADE, related_name="parts")
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    name = models.CharField(max_length=100)

    class Meta:
        db_table = "parts_used"


class Invoice(models.Model):
    STATUS_CHOICES = [("unpaid", "Unpaid"), ("paid", "Paid")]
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name="invoices")
    labor_total = models.DecimalField(max_digits=10, decimal_places=2)
    parts_total = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    payment_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="unpaid")

    class Meta:
        db_table = "invoices"
        constraints = [
            models.UniqueConstraint(fields=["appointment"], name="unique_invoice_per_appointment"),
        ]


class Employee(models.Model):
    name = models.CharField(max_length=100)
    username = models.CharField(max_length=50, unique=True)
    password_hash = models.CharField(max_length=255)

    class Meta:
        db_table = "employees"

    def __str__(self):
        return self.name


class Review(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField()
    date = models.DateField(auto_now_add=True)

    class Meta:
        db_table = "reviews"

    @property
    def stars(self):
        return "\u2605" * self.rating + "\u2606" * (5 - self.rating)


class ContactMessage(models.Model):
    """Stores submissions from the About and Contact form."""
    name = models.CharField(max_length=100)
    email = models.EmailField(max_length=255)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "contact_messages"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.created_at:%Y-%m-%d})"
