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


from decimal import Decimal  # noqa: E402

from django.contrib.auth.hashers import check_password  # noqa: E402

from .models import Service  # noqa: E402


def make_customer(username="sam", password="correct-horse-1"):
    from django.contrib.auth.hashers import make_password
    return Customer.objects.create(
        name="Sam", phone="555-0100", email="sam@example.com",
        username=username, password_hash=make_password(password),
    )


class ServicesPageTests(TestCase):
    def test_seeded_services_are_listed(self):
        response = self.client.get("/services/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Oil &amp; Filter Change")
        self.assertGreaterEqual(Service.objects.count(), 8)

    def test_guest_sees_login_prompt_not_add_button(self):
        response = self.client.get("/services/")
        self.assertContains(response, "to add services to your cart")
        self.assertNotContains(response, "Add to cart")

    def test_new_service_shows_up(self):
        Service.objects.create(name="Dyno Session", description="Power run", price=Decimal("99.00"))
        self.assertContains(self.client.get("/services/"), "Dyno Session")


class RegistrationTests(TestCase):
    data = {
        "name": "Sam", "phone": "555-0100", "email": "sam@example.com",
        "username": "sam", "password": "correct-horse-1", "confirm_password": "correct-horse-1",
    }

    def test_register_creates_customer_with_hashed_password_and_logs_in(self):
        response = self.client.post("/register/", self.data)
        self.assertRedirects(response, "/services/")
        customer = Customer.objects.get(username="sam")
        self.assertNotEqual(customer.password_hash, "correct-horse-1")
        self.assertTrue(check_password("correct-horse-1", customer.password_hash))
        self.assertEqual(self.client.session["customer_id"], customer.pk)

    def test_mismatched_passwords_rejected(self):
        response = self.client.post("/register/", {**self.data, "confirm_password": "different-pass-2"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Customer.objects.count(), 0)

    def test_short_password_rejected(self):
        response = self.client.post("/register/", {**self.data, "password": "short", "confirm_password": "short"})
        self.assertEqual(Customer.objects.count(), 0)
        self.assertEqual(response.status_code, 200)

    def test_duplicate_username_rejected(self):
        make_customer("sam")
        response = self.client.post("/register/", self.data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Customer.objects.filter(username="sam").count(), 1)


class LoginTests(TestCase):
    def setUp(self):
        self.customer = make_customer()

    def test_login_success(self):
        response = self.client.post("/login/", {"username": "sam", "password": "correct-horse-1"})
        self.assertRedirects(response, "/services/")
        self.assertEqual(self.client.session["customer_id"], self.customer.pk)

    def test_wrong_password_rejected(self):
        response = self.client.post("/login/", {"username": "sam", "password": "nope"})
        self.assertContains(response, "Invalid username or password.")
        self.assertNotIn("customer_id", self.client.session)

    def test_unknown_user_rejected_with_same_message(self):
        response = self.client.post("/login/", {"username": "ghost", "password": "whatever-1"})
        self.assertContains(response, "Invalid username or password.")

    def test_logout_requires_post_and_clears_session(self):
        self.client.post("/login/", {"username": "sam", "password": "correct-horse-1"})
        self.assertEqual(self.client.get("/logout/").status_code, 405)
        self.client.post("/logout/")
        self.assertNotIn("customer_id", self.client.session)

    def test_login_ignores_offsite_next(self):
        response = self.client.post(
            "/login/", {"username": "sam", "password": "correct-horse-1", "next": "https://evil.example/"}
        )
        self.assertRedirects(response, "/services/")


class CartTests(TestCase):
    def setUp(self):
        self.customer = make_customer()
        self.a = Service.objects.create(name="Svc A", description="a", price=Decimal("10.50"))
        self.b = Service.objects.create(name="Svc B", description="b", price=Decimal("20.25"))

    def login(self):
        self.client.post("/login/", {"username": "sam", "password": "correct-horse-1"})

    def test_guest_cannot_add_to_cart(self):
        response = self.client.post("/cart/add/", {"service_id": self.a.pk})
        self.assertRedirects(response, "/login/?next=/services/")
        self.assertNotIn("cart", self.client.session)

    def test_guest_cannot_view_cart(self):
        self.assertRedirects(self.client.get("/cart/"), "/login/?next=/cart/")

    def test_add_view_total_and_remove(self):
        self.login()
        self.client.post("/cart/add/", {"service_id": self.a.pk})
        self.client.post("/cart/add/", {"service_id": self.b.pk})
        response = self.client.get("/cart/")
        self.assertContains(response, "Svc A")
        self.assertContains(response, "Svc B")
        self.assertContains(response, "$30.75")
        self.client.post("/cart/remove/", {"service_id": self.a.pk})
        response = self.client.get("/cart/")
        self.assertNotContains(response, "Svc A")
        self.assertContains(response, "$20.25")

    def test_adding_same_service_twice_keeps_one_entry(self):
        self.login()
        self.client.post("/cart/add/", {"service_id": self.a.pk})
        self.client.post("/cart/add/", {"service_id": self.a.pk})
        self.assertEqual(self.client.session["cart"], [self.a.pk])

    def test_unknown_service_returns_404(self):
        self.login()
        self.assertEqual(self.client.post("/cart/add/", {"service_id": 99999}).status_code, 404)

    def test_logout_clears_cart(self):
        self.login()
        self.client.post("/cart/add/", {"service_id": self.a.pk})
        self.client.post("/logout/")
        self.assertNotIn("cart", self.client.session)

    def test_add_to_cart_button_shown_when_logged_in(self):
        self.login()
        self.assertContains(self.client.get("/services/"), "Add to cart")
