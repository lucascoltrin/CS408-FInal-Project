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
        "name": "Sam", "phone": "555-010-0100", "email": "sam@example.com",
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


# ---------------------------------------------------------------- Checkpoint 3

from django.db import IntegrityError as _IntegrityError  # noqa: E402
from django.utils import timezone  # noqa: E402

from .models import AppointmentService  # noqa: E402


def future(days=7):
    return timezone.localdate() + datetime.timedelta(days=days)


class PhoneValidationTests(TestCase):
    base = {
        "name": "Sam", "email": "sam@example.com", "username": "sam",
        "password": "correct-horse-1", "confirm_password": "correct-horse-1",
    }

    def test_common_formats_are_normalized(self):
        for raw in ["(555) 010-0100", "555-010-0100", "+1 555 010 0100", "5550100100"]:
            Customer.objects.all().delete()
            self.client.post("/register/", {**self.base, "phone": raw})
            self.assertEqual(Customer.objects.get().phone, "555-010-0100", raw)
            self.client.post("/logout/")

    def test_bad_numbers_are_rejected(self):
        for raw in ["123", "abcdefghij", "555-010-0100x", "555 010 0100 ext 5"]:
            response = self.client.post("/register/", {**self.base, "phone": raw})
            self.assertContains(response, "10-digit phone number", msg_prefix=raw)
            self.assertEqual(Customer.objects.count(), 0, raw)

    def test_guest_prefix_username_is_reserved(self):
        response = self.client.post("/register/", {**self.base, "phone": "555-010-0100", "username": "Guest-abc"})
        self.assertContains(response, "cannot start with")
        self.assertEqual(Customer.objects.count(), 0)


class VehicleConstraintTests(TestCase):
    def test_plate_is_unique_per_customer_only(self):
        a, b = make_customer("a"), make_customer("b")
        Vehicle.objects.create(customer=a, make="M", model="X", year=2000, plate="ABC123")
        Vehicle.objects.create(customer=b, make="M", model="X", year=2000, plate="ABC123")  # other customer: fine
        with self.assertRaises(_IntegrityError), transaction.atomic():
            Vehicle.objects.create(customer=a, make="M", model="Y", year=2001, plate="ABC123")


class BookingPageTests(TestCase):
    def setUp(self):
        self.svc = Service.objects.create(name="Svc A", description="a", price=Decimal("10.00"))

    def test_guest_form_asks_for_contact_info_and_lists_services(self):
        response = self.client.get("/book/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your info")
        self.assertContains(response, "Svc A - $10.00")
        self.assertNotIn("vehicle", response.context["form"].fields)

    def test_logged_in_form_skips_contact_info_and_prechecks_cart(self):
        make_customer()
        self.client.post("/login/", {"username": "sam", "password": "correct-horse-1"})
        self.client.post("/cart/add/", {"service_id": self.svc.pk})
        response = self.client.get("/book/")
        self.assertNotContains(response, "Your info")
        self.assertEqual(response.context["form"].initial["services"], [self.svc.pk])


class GuestBookingTests(TestCase):
    def setUp(self):
        self.svc_a = Service.objects.create(name="Svc A", description="a", price=Decimal("10.00"))
        self.svc_b = Service.objects.create(name="Svc B", description="b", price=Decimal("20.50"))

    def data(self, **overrides):
        base = {
            "name": "Gus", "phone": "(555) 010-0199", "email": "gus@example.com",
            "make": "Subaru", "model": "WRX", "year": "2018", "plate": "abc 123",
            "services": [self.svc_a.pk, self.svc_b.pk],
            "date": future().isoformat(), "time": "10:30",
        }
        base.update(overrides)
        return base

    def test_booking_writes_customer_vehicle_appointment_and_services(self):
        response = self.client.post("/book/", self.data())
        self.assertRedirects(response, "/book/confirmed/")
        customer = Customer.objects.get()
        self.assertTrue(customer.is_guest)
        self.assertEqual(customer.phone, "555-010-0199")
        vehicle = Vehicle.objects.get()
        self.assertEqual((vehicle.customer, vehicle.plate), (customer, "ABC123"))
        appointment = Appointment.objects.get()
        self.assertEqual((appointment.vehicle, appointment.status), (vehicle, "pending"))
        self.assertEqual(AppointmentService.objects.filter(appointment=appointment).count(), 2)
        self.assertEqual(AppointmentService.objects.first().status, "pending")

    def test_guest_account_can_never_log_in(self):
        self.client.post("/book/", self.data())
        username = Customer.objects.get().username
        response = self.client.post("/login/", {"username": username, "password": ""})
        self.assertNotIn("customer_id", self.client.session)
        self.assertEqual(response.status_code, 200)

    def test_confirmation_shows_booking_and_total(self):
        self.client.post("/book/", self.data())
        response = self.client.get("/book/confirmed/")
        self.assertContains(response, "Appointment requested")
        self.assertContains(response, "Svc A")
        self.assertContains(response, "$30.50")
        self.assertContains(response, "ABC123")

    def test_confirmation_without_a_booking_redirects(self):
        self.assertRedirects(self.client.get("/book/confirmed/"), "/book/")

    def test_repeat_guest_reuses_customer_and_vehicle(self):
        self.client.post("/book/", self.data())
        self.client.post("/book/", self.data(phone="555-010-0199", plate="ABC-123", name="Gus R"))
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(Customer.objects.get().name, "Gus R")
        self.assertEqual(Vehicle.objects.count(), 1)
        self.assertEqual(Appointment.objects.count(), 2)

    def test_guest_is_not_attached_to_a_registered_account_with_same_phone(self):
        member = make_customer()
        member.phone = "555-010-0199"
        member.save()
        self.client.post("/book/", self.data())
        self.assertEqual(Customer.objects.count(), 2)
        self.assertEqual(member.vehicles.count(), 0)

    def assert_rejected(self, **overrides):
        response = self.client.post("/book/", self.data(**overrides))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Appointment.objects.count(), 0)
        self.assertEqual(Customer.objects.count(), 0)
        return response

    def test_no_services_rejected(self):
        self.assertContains(self.assert_rejected(services=[]), "Choose at least one service.")

    def test_past_date_rejected(self):
        self.assertContains(self.assert_rejected(date=future(-1).isoformat()), "today or a future date")

    def test_date_more_than_a_year_out_rejected(self):
        self.assertContains(self.assert_rejected(date=future(400).isoformat()), "within the next year")

    def test_missing_vehicle_details_rejected(self):
        self.assert_rejected(make="", plate="")

    def test_bad_year_rejected(self):
        self.assert_rejected(year="1850")
        self.assert_rejected(year="3000")

    def test_bad_phone_rejected(self):
        self.assertContains(self.assert_rejected(phone="123"), "10-digit phone number")

    def test_plate_with_symbols_rejected(self):
        self.assert_rejected(plate="AB$12")

    def test_missing_contact_info_rejected(self):
        self.assert_rejected(name="", email="")


class LoggedInBookingTests(TestCase):
    def setUp(self):
        self.customer = make_customer()
        self.svc = Service.objects.create(name="Svc A", description="a", price=Decimal("10.00"))
        self.client.post("/login/", {"username": "sam", "password": "correct-horse-1"})

    def data(self, **overrides):
        base = {
            "make": "Honda", "model": "Civic", "year": "2012", "plate": "xyz789",
            "services": [self.svc.pk], "date": future().isoformat(), "time": "09:00",
        }
        base.update(overrides)
        return base

    def test_new_vehicle_is_saved_to_the_account_and_cart_is_cleared(self):
        self.client.post("/cart/add/", {"service_id": self.svc.pk})
        response = self.client.post("/book/", self.data())
        self.assertRedirects(response, "/book/confirmed/")
        self.assertEqual(Customer.objects.count(), 1)  # no guest record created
        self.assertEqual(self.customer.vehicles.get().plate, "XYZ789")
        self.assertEqual(Appointment.objects.get().vehicle.customer, self.customer)
        self.assertEqual(self.client.session["cart"], [])

    def test_saved_vehicle_can_be_chosen(self):
        vehicle = Vehicle.objects.create(customer=self.customer, make="Subaru", model="WRX", year=2018, plate="ABC123")
        response = self.client.post("/book/", {
            "vehicle": vehicle.pk, "services": [self.svc.pk], "date": future().isoformat(), "time": "09:00",
        })
        self.assertRedirects(response, "/book/confirmed/")
        self.assertEqual(Vehicle.objects.count(), 1)
        self.assertEqual(Appointment.objects.get().vehicle, vehicle)

    def test_cannot_book_on_someone_elses_vehicle(self):
        other = make_customer("other")
        theirs = Vehicle.objects.create(customer=other, make="Ford", model="F150", year=2015, plate="THEIRS1")
        Vehicle.objects.create(customer=self.customer, make="Subaru", model="WRX", year=2018, plate="ABC123")
        response = self.client.post("/book/", {
            "vehicle": theirs.pk, "services": [self.svc.pk], "date": future().isoformat(), "time": "09:00",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Appointment.objects.count(), 0)

    def test_new_vehicle_details_required_when_no_saved_vehicle_chosen(self):
        Vehicle.objects.create(customer=self.customer, make="Subaru", model="WRX", year=2018, plate="ABC123")
        response = self.client.post("/book/", {
            "vehicle": "", "services": [self.svc.pk], "date": future().isoformat(), "time": "09:00",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Appointment.objects.count(), 0)
