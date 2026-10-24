from decimal import Decimal

from django.db import migrations

SERVICES = [
    ("Oil & Filter Change", "Full synthetic oil and a new filter.", "65.00"),
    ("Tire Rotation & Balance", "Rotate and balance all four tires.", "40.00"),
    ("Brake Pad Replacement", "Replace front or rear pads and inspect rotors.", "180.00"),
    ("Diagnostic Scan", "Read codes and inspect to find the cause of a warning light.", "75.00"),
    ("Intake Installation", "Install an aftermarket cold air or short ram intake.", "150.00"),
    ("Exhaust Installation", "Install a cat-back or axle-back exhaust system.", "250.00"),
    ("Coilover Installation", "Install and set ride height on a coilover kit.", "300.00"),
    ("ECU Tune", "Custom engine tune for your setup.", "500.00"),
]


def add_services(apps, schema_editor):
    Service = apps.get_model("shop", "Service")
    for name, description, price in SERVICES:
        Service.objects.get_or_create(
            name=name, defaults={"description": description, "price": Decimal(price)}
        )


def remove_services(apps, schema_editor):
    Service = apps.get_model("shop", "Service")
    Service.objects.filter(name__in=[name for name, _, _ in SERVICES]).delete()


class Migration(migrations.Migration):
    dependencies = [("shop", "0001_initial")]
    operations = [migrations.RunPython(add_services, remove_services)]
