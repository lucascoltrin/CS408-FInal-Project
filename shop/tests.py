import datetime

from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import Appointment, ContactMessage, Customer, Vehicle


class PageTests(TestCase):
    def test_landing_page_has_header_and_footer(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<header>")
        self.assertContains(response, "<footer")
        self.assertContains(response, 'href="/about/"')

    def test_about_page_shows_contact_form(self):
        response = self.client.get("/about/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<form")


class ContactFormTests(TestCase):
    def test_valid_submission_is_saved(self):
        response = self.client.post("/about/", {"name": "Sam", "email": "sam@example.com", "message": "Hi"})
        self.assertRedirects(response, "/about/?sent=1")
        self.assertEqual(ContactMessage.objects.count(), 1)

    def test_missing_email_is_rejected(self):
        response = self.client.post("/about/", {"name": "Sam", "email": "", "message": "Hi"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ContactMessage.objects.count(), 0)


class ModelTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            name="Sam", phone="555-0100", email="sam@example.com", username="sam", password_hash="x"
        )
        self.vehicle = Vehicle.objects.create(
            customer=self.customer, make="Subaru", model="WRX", year=2018, plate="ABC123"
        )

    def test_appointment_requires_a_vehicle(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Appointment.objects.create(date=datetime.date(2026, 11, 1), time=datetime.time(9, 0))

    def test_appointment_defaults_to_pending(self):
        appt = Appointment.objects.create(
            vehicle=self.vehicle, date=datetime.date(2026, 11, 1), time=datetime.time(9, 0)
        )
        self.assertEqual(appt.status, "pending")

    def test_deleting_customer_deletes_their_vehicles(self):
        self.customer.delete()
        self.assertEqual(Vehicle.objects.count(), 0)
