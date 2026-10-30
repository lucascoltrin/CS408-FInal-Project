from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


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
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name="invoices")
    labor_total = models.DecimalField(max_digits=10, decimal_places=2)
    parts_total = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    payment_status = models.CharField(max_length=20, default="unpaid")

    class Meta:
        db_table = "invoices"


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
