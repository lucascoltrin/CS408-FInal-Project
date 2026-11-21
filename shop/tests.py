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


# ---------------------------------------------------------------- Checkpoint 4

from django.contrib.auth.hashers import make_password as _make_password  # noqa: E402


def make_guest(phone="555-010-0199", username="guest-abc"):
    return Customer.objects.create(
        name="Gus", phone=phone, email="gus@example.com",
        username=username, password_hash=_make_password(None),
    )


def make_booking(customer, plate="ABC123", date=None, status="pending", services=()):
    vehicle, _ = Vehicle.objects.get_or_create(
        customer=customer, plate=plate, defaults={"make": "Subaru", "model": "WRX", "year": 2018},
    )
    appointment = Appointment.objects.create(
        vehicle=vehicle, date=date or future(), time=datetime.time(9, 0), status=status,
    )
    for service in services:
        AppointmentService.objects.create(appointment=appointment, service=service)
    return appointment


class HistoryLookupTests(TestCase):
    def setUp(self):
        self.svc = Service.objects.create(name="Svc A", description="a", price=Decimal("10.00"))
        self.guest = make_guest()
        self.appt = make_booking(self.guest, services=[self.svc], status="approved")
        other = make_guest(phone="555-010-0200", username="guest-other")
        make_booking(other, plate="OTHER99", services=[self.svc])

    def lookup(self, plate="ABC123", phone="555-010-0199"):
        return self.client.post("/history/", {"plate": plate, "phone": phone})

    def test_guest_page_lists_no_vehicles_until_lookup(self):
        response = self.client.get("/history/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Look up a vehicle")
        self.assertNotContains(response, "ABC123")
        self.assertNotContains(response, "OTHER99")

    def test_matching_plate_and_phone_shows_history(self):
        response = self.lookup()
        self.assertContains(response, "2018 Subaru WRX (ABC123)")
        self.assertContains(response, "Svc A")
        self.assertContains(response, "Approved")

    def test_formatting_of_plate_and_phone_does_not_matter(self):
        self.assertContains(self.lookup("abc-123", "(555) 010-0199"), "ABC123")

    def test_wrong_phone_shows_nothing(self):
        response = self.lookup(phone="555-010-0200")
        self.assertContains(response, "No vehicle found")
        self.assertNotContains(response, "Svc A")

    def test_unknown_plate_gets_the_same_message(self):
        self.assertContains(self.lookup("NOPE000"), "No vehicle found")

    def test_other_customers_data_is_never_shown(self):
        response = self.lookup()
        self.assertNotContains(response, "OTHER99")
        self.assertNotContains(response, "gus@example.com")

    def test_invalid_phone_and_blank_plate_are_rejected(self):
        self.assertContains(self.lookup(phone="123"), "10-digit phone number")
        self.assertContains(self.lookup(plate=" - "), "Enter a license plate.")

    def test_completed_service_shows_its_cost(self):
        row = AppointmentService.objects.get(appointment=self.appt)
        row.cost = Decimal("42.00")
        row.save()
        self.assertContains(self.lookup(), "$42.00")

    def test_guest_cannot_change_appointments(self):
        self.assertNotContains(self.lookup(), "Change")

    def test_every_matching_vehicle_is_shown(self):
        member = make_customer()
        member.phone = "555-010-0199"
        member.save()
        make_booking(member, plate="ABC123")
        response = self.lookup()
        self.assertEqual(len(response.context["lookup_results"]), 2)


class LoggedInHistoryTests(TestCase):
    def setUp(self):
        self.svc = Service.objects.create(name="Svc A", description="a", price=Decimal("10.00"))
        self.me = make_customer()
        self.client.post("/login/", {"username": "sam", "password": "correct-horse-1"})

    def test_empty_state(self):
        self.assertContains(self.client.get("/history/"), "You have no vehicles yet")

    def test_shows_only_my_vehicles_with_status(self):
        make_booking(self.me, plate="MINE123", services=[self.svc], status="in_progress")
        make_booking(make_customer("other"), plate="THEIRS1", services=[self.svc])
        response = self.client.get("/history/")
        self.assertContains(response, "MINE123")
        self.assertContains(response, "In progress")
        self.assertNotContains(response, "THEIRS1")

    def test_change_link_only_on_upcoming_open_appointments(self):
        upcoming = make_booking(self.me, plate="UP1", status="pending")
        done = make_booking(self.me, plate="DONE1", status="completed")
        past = make_booking(self.me, plate="PAST1", date=future(-3), status="pending")
        response = self.client.get("/history/")
        self.assertContains(response, f"/appointments/{upcoming.pk}/edit/")
        self.assertNotContains(response, f"/appointments/{done.pk}/edit/")
        self.assertNotContains(response, f"/appointments/{past.pk}/edit/")

    def test_lookup_form_is_still_available(self):
        self.assertContains(self.client.get("/history/"), "Booked without an account?")


class AppointmentEditTests(TestCase):
    def setUp(self):
        self.a = Service.objects.create(name="Svc A", description="a", price=Decimal("10.00"))
        self.b = Service.objects.create(name="Svc B", description="b", price=Decimal("20.00"))
        self.c = Service.objects.create(name="Svc C", description="c", price=Decimal("30.00"))
        self.me = make_customer()
        self.appt = make_booking(self.me, services=[self.a, self.b], status="approved")
        self.url = f"/appointments/{self.appt.pk}/edit/"

    def login(self, username="sam"):
        self.client.post("/login/", {"username": username, "password": "correct-horse-1"})

    def post(self, **overrides):
        data = {"services": [self.b.pk, self.c.pk], "date": future(10).isoformat(), "time": "14:15"}
        data.update(overrides)
        return self.client.post(self.url, data)

    def test_login_required(self):
        self.assertRedirects(self.client.get(self.url), f"/login/?next={self.url}")
        self.assertRedirects(self.client.post(self.url, {}), "/login/?next=/services/")

    def test_form_is_prefilled(self):
        self.login()
        initial = self.client.get(self.url).context["form"].initial
        self.assertEqual(set(initial["services"]), {self.a.pk, self.b.pk})
        self.assertEqual(initial["date"], self.appt.date)

    def test_update_changes_date_time_services_and_resets_status(self):
        self.login()
        kept_row = AppointmentService.objects.get(appointment=self.appt, service=self.b)
        self.assertRedirects(self.post(), "/history/")
        self.appt.refresh_from_db()
        self.assertEqual((self.appt.date, self.appt.time), (future(10), datetime.time(14, 15)))
        self.assertEqual(self.appt.status, "pending")
        services = set(self.appt.appointment_services.values_list("service_id", flat=True))
        self.assertEqual(services, {self.b.pk, self.c.pk})
        self.assertTrue(AppointmentService.objects.filter(pk=kept_row.pk).exists())  # kept, not recreated

    def test_other_customers_cannot_touch_it(self):
        make_customer("other")
        self.login("other")
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.post().status_code, 404)
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, "approved")

    def test_completed_appointment_cannot_be_changed(self):
        self.appt.status = "completed"
        self.appt.save()
        self.login()
        self.assertRedirects(self.post(), "/history/")
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.date, future())

    def test_past_appointment_cannot_be_changed(self):
        self.appt.date = future(-2)
        self.appt.save()
        self.login()
        self.assertRedirects(self.client.get(self.url), "/history/")

    def test_invalid_changes_are_rejected(self):
        self.login()
        self.assertContains(self.post(date=future(-1).isoformat()), "today or a future date")
        self.assertContains(self.post(services=[]), "Choose at least one service.")
        self.appt.refresh_from_db()
        self.assertEqual((self.appt.status, self.appt.date), ("approved", future()))


# ---------------------------------------------------------------- Checkpoint 5

from io import StringIO  # noqa: E402
from unittest import mock  # noqa: E402

from django.core.management import call_command  # noqa: E402
from django.core.management.base import CommandError  # noqa: E402

from .models import Employee  # noqa: E402

STAFF_PW = "owner-pass-1"


def make_employee(username="owner", password=STAFF_PW):
    return Employee.objects.create(name="Owner", username=username, password_hash=_make_password(password))


class StaffTestCase(TestCase):
    def staff_login(self):
        make_employee()
        self.client.post("/staff/login/", {"username": "owner", "password": STAFF_PW})


class StaffLoginTests(StaffTestCase):
    def test_login_success_opens_dashboard(self):
        make_employee()
        response = self.client.post("/staff/login/", {"username": "owner", "password": STAFF_PW})
        self.assertRedirects(response, "/dashboard/")
        self.assertEqual(self.client.get("/dashboard/").status_code, 200)

    def test_bad_credentials_share_one_message(self):
        make_employee()
        for creds in [{"username": "owner", "password": "wrong-pass-1"}, {"username": "ghost", "password": "wrong-pass-1"}]:
            response = self.client.post("/staff/login/", creds)
            self.assertContains(response, "Invalid username or password.")
            self.assertNotIn("employee_id", self.client.session)

    def test_visitors_are_sent_to_staff_login(self):
        self.assertRedirects(self.client.get("/dashboard/"), "/staff/login/?next=/dashboard/")

    def test_customer_login_does_not_grant_dashboard_access(self):
        make_customer()
        self.client.post("/login/", {"username": "sam", "password": "correct-horse-1"})
        self.assertRedirects(self.client.get("/dashboard/"), "/staff/login/?next=/dashboard/")

    def test_staff_cannot_log_in_through_the_customer_form(self):
        make_employee()
        response = self.client.post("/login/", {"username": "owner", "password": STAFF_PW})
        self.assertContains(response, "Invalid username or password.")

    def test_logout_requires_post_and_ends_access(self):
        self.staff_login()
        self.assertEqual(self.client.get("/staff/logout/").status_code, 405)
        self.client.post("/staff/logout/")
        self.assertRedirects(self.client.get("/dashboard/"), "/staff/login/?next=/dashboard/")

    def test_offsite_next_is_ignored(self):
        make_employee()
        response = self.client.post(
            "/staff/login/", {"username": "owner", "password": STAFF_PW, "next": "https://evil.example/"},
        )
        self.assertRedirects(response, "/dashboard/")

    def test_public_pages_do_not_link_to_staff_login(self):
        for url in ["/", "/about/", "/services/", "/history/", "/book/"]:
            self.assertNotContains(self.client.get(url), "/staff/login/")

    def test_staff_see_dashboard_link_in_nav(self):
        self.staff_login()
        self.assertContains(self.client.get("/"), "Staff log out")

    def test_deleted_employee_loses_access(self):
        self.staff_login()
        Employee.objects.all().delete()
        self.assertRedirects(self.client.get("/dashboard/"), "/staff/login/?next=/dashboard/")


class DashboardListTests(StaffTestCase):
    def setUp(self):
        self.svc = Service.objects.create(name="Svc A", description="a", price=Decimal("10.00"))
        self.member = make_customer()
        self.member.phone = "555-010-0101"
        self.member.save()
        self.guest = make_guest()
        self.soon = make_booking(self.member, plate="SOON1", date=future(2), services=[self.svc])
        self.later = make_booking(self.guest, plate="LATER1", date=future(9), status="approved", services=[self.svc])
        self.old = make_booking(self.member, plate="OLD1", date=future(-5), status="completed", services=[self.svc])
        self.staff_login()

    def test_lists_every_appointment_with_customer_and_vehicle(self):
        response = self.client.get("/dashboard/")
        for text in ["SOON1", "LATER1", "OLD1", "555-010-0101", "555-010-0199", "Svc A"]:
            self.assertContains(response, text)

    def test_guest_bookings_are_marked(self):
        self.assertContains(self.client.get("/dashboard/"), "Guest")

    def test_upcoming_first_soonest_first_then_past(self):
        order = [a.pk for a in self.client.get("/dashboard/").context["appointments"]]
        self.assertEqual(order, [self.soon.pk, self.later.pk, self.old.pk])

    def test_status_filter_and_counts(self):
        response = self.client.get("/dashboard/?status=pending")
        self.assertEqual([a.pk for a in response.context["appointments"]], [self.soon.pk])
        counts = {key: count for key, _, count in response.context["tabs"]}
        self.assertEqual((counts[""], counts["pending"], counts["approved"], counts["completed"]), (3, 1, 1, 1))

    def test_unknown_filter_shows_all(self):
        self.assertEqual(len(self.client.get("/dashboard/?status=bogus").context["appointments"]), 3)


class DashboardActionTests(StaffTestCase):
    def setUp(self):
        self.member = make_customer()
        self.appt = make_booking(self.member, services=[])
        self.url = f"/dashboard/appointments/{self.appt.pk}/action/"

    def test_approve_and_deny(self):
        self.staff_login()
        self.client.post(self.url, {"action": "approve"})
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, "approved")
        self.client.post(self.url, {"action": "deny"})
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, "denied")

    def test_customer_sees_the_new_status(self):
        self.staff_login()
        self.client.post(self.url, {"action": "approve"})
        self.client.post("/staff/logout/")
        self.client.post("/login/", {"username": "sam", "password": "correct-horse-1"})
        self.assertContains(self.client.get("/history/"), "Approved")

    def test_get_is_not_allowed(self):
        self.staff_login()
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_unknown_action_rejected(self):
        self.staff_login()
        self.assertEqual(self.client.post(self.url, {"action": "explode"}).status_code, 400)
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, "pending")

    def test_requires_staff(self):
        self.client.post(self.url, {"action": "approve"})
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, "pending")


class ManageAppointmentTests(StaffTestCase):
    def setUp(self):
        self.a = Service.objects.create(name="Svc A", description="a", price=Decimal("10.00"))
        self.b = Service.objects.create(name="Svc B", description="b", price=Decimal("20.00"))
        self.c = Service.objects.create(name="Svc C", description="c", price=Decimal("30.00"))
        self.member = make_customer()
        self.appt = make_booking(self.member, services=[self.a, self.b])
        self.other = make_booking(self.member, plate="OTHER1", services=[self.a])
        self.url = f"/dashboard/appointments/{self.appt.pk}/"
        self.rows = list(self.appt.appointment_services.order_by("id"))
        self.staff_login()

    def payload(self, status="approved", time="11:00", add="", row_fields=None):
        data = {
            "status": status, "date": self.appt.date.isoformat(), "time": time,
            "services-TOTAL_FORMS": len(self.rows), "services-INITIAL_FORMS": len(self.rows),
            "services-MIN_NUM_FORMS": 0, "services-MAX_NUM_FORMS": 1000, "add-service": add,
        }
        for i, row in enumerate(self.rows):
            data.update({
                f"services-{i}-id": row.pk, f"services-{i}-status": row.status,
                f"services-{i}-hours": "", f"services-{i}-cost": "", f"services-{i}-date_completed": "",
            })
            data.update((row_fields or {}).get(i, {}))
        return data

    def test_page_shows_customer_vehicle_and_services(self):
        response = self.client.get(self.url)
        for text in ["Sam", "555-0100", "ABC123", "Svc A", "Svc B"]:
            self.assertContains(response, text)

    def test_update_status_and_time(self):
        self.assertRedirects(self.client.post(self.url, self.payload(status="in_progress", time="13:45")), self.url)
        self.appt.refresh_from_db()
        self.assertEqual((self.appt.status, self.appt.time), ("in_progress", datetime.time(13, 45)))

    def test_update_service_rows_and_default_completion_date(self):
        fields = {0: {"services-0-status": "completed", "services-0-hours": "1.5", "services-0-cost": "99.99"}}
        self.client.post(self.url, self.payload(row_fields=fields))
        row = AppointmentService.objects.get(pk=self.rows[0].pk)
        self.assertEqual((row.status, row.hours, row.cost), ("completed", Decimal("1.50"), Decimal("99.99")))
        self.assertEqual(row.date_completed, timezone.localdate())

    def test_remove_a_service(self):
        fields = {1: {"services-1-DELETE": "on"}}
        self.client.post(self.url, self.payload(row_fields=fields))
        remaining = set(self.appt.appointment_services.values_list("service_id", flat=True))
        self.assertEqual(remaining, {self.a.pk})

    def test_add_a_service(self):
        self.client.post(self.url, self.payload(add=self.c.pk))
        services = set(self.appt.appointment_services.values_list("service_id", flat=True))
        self.assertEqual(services, {self.a.pk, self.b.pk, self.c.pk})

    def test_already_listed_service_cannot_be_added_again(self):
        response = self.client.post(self.url, self.payload(add=self.a.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.appt.appointment_services.count(), 2)

    def test_negative_cost_is_rejected_and_nothing_is_saved(self):
        fields = {0: {"services-0-cost": "-5"}}
        response = self.client.post(self.url, self.payload(status="completed", row_fields=fields))
        self.assertEqual(response.status_code, 200)
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, "pending")

    def test_other_appointments_are_untouched(self):
        self.client.post(self.url, self.payload(status="denied"))
        self.other.refresh_from_db()
        self.assertEqual(self.other.status, "pending")

    def test_requires_staff(self):
        self.client.post("/staff/logout/")
        self.assertRedirects(self.client.get(self.url), f"/staff/login/?next={self.url}")
        self.client.post(self.url, self.payload(status="denied"))
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, "pending")

    def test_unknown_appointment_is_404(self):
        self.assertEqual(self.client.get("/dashboard/appointments/99999/").status_code, 404)


class DeleteAppointmentTests(StaffTestCase):
    def setUp(self):
        self.svc = Service.objects.create(name="Svc A", description="a", price=Decimal("10.00"))
        self.member = make_customer()
        self.appt = make_booking(self.member, services=[self.svc])
        self.url = f"/dashboard/appointments/{self.appt.pk}/delete/"

    def test_get_asks_for_confirmation_and_deletes_nothing(self):
        self.staff_login()
        self.assertContains(self.client.get(self.url), "Delete this appointment?")
        self.assertEqual(Appointment.objects.count(), 1)

    def test_post_deletes_appointment_and_its_services_but_keeps_the_vehicle(self):
        self.staff_login()
        self.assertRedirects(self.client.post(self.url), "/dashboard/")
        self.assertEqual(Appointment.objects.count(), 0)
        self.assertEqual(AppointmentService.objects.count(), 0)
        self.assertEqual(Vehicle.objects.count(), 1)

    def test_requires_staff(self):
        self.client.post(self.url)
        self.assertEqual(Appointment.objects.count(), 1)


class CreateEmployeeCommandTests(TestCase):
    def run_command(self, *args, **kwargs):
        return call_command("create_employee", *args, stdout=StringIO(), **kwargs)

    def test_creates_a_login_with_a_hashed_password(self):
        self.run_command("--username", "owner", "--name", "The Owner", "--password", "owner-pass-1")
        employee = Employee.objects.get(username="owner")
        self.assertEqual(employee.name, "The Owner")
        self.assertNotEqual(employee.password_hash, "owner-pass-1")
        self.assertTrue(check_password("owner-pass-1", employee.password_hash))

    def test_duplicate_username_is_refused(self):
        make_employee()
        with self.assertRaises(CommandError):
            self.run_command("--username", "owner", "--password", "another-pass-1")

    def test_short_password_is_refused(self):
        with self.assertRaises(CommandError):
            self.run_command("--username", "owner", "--password", "short")
        self.assertEqual(Employee.objects.count(), 0)

    def test_reset_password(self):
        make_employee()
        self.run_command("--username", "owner", "--password", "brand-new-pass-1", "--reset-password")
        self.assertTrue(check_password("brand-new-pass-1", Employee.objects.get().password_hash))

    def test_reset_for_unknown_user_is_refused(self):
        with self.assertRaises(CommandError):
            self.run_command("--username", "ghost", "--password", "brand-new-pass-1", "--reset-password")

    def test_prompt_mismatch_is_refused(self):
        with mock.patch("shop.management.commands.create_employee.getpass", side_effect=["aaaaaaaa1", "bbbbbbbb2"]):
            with self.assertRaises(CommandError):
                self.run_command("--username", "owner")


# ---------------------------------------------------------------- Logo

class LogoTests(TestCase):
    def test_header_uses_the_white_logo_on_every_page(self):
        for url in ["/", "/about/", "/services/", "/book/"]:
            self.assertContains(self.client.get(url), "shop/img/logo-white.png", msg_prefix=url)

    def test_home_hero_uses_the_black_logo_with_alt_text(self):
        response = self.client.get("/")
        self.assertContains(response, "shop/img/logo.png")
        self.assertContains(response, 'alt="SF Performance"')

    def test_logo_files_are_served(self):
        for name in ["logo.png", "logo-white.png"]:
            response = self.client.get(f"/static/shop/img/{name}")
            self.assertEqual(response.status_code, 200, name)
            self.assertEqual(response["Content-Type"], "image/png", name)
            response.close()


# ---------------------------------------------------------------- Checkpoint 6

from . import billing  # noqa: E402
from .models import Invoice, PartUsed, Review  # noqa: E402


def add_part(row, name="Filter", quantity=1, price="10.00"):
    return PartUsed.objects.create(appointment_service=row, name=name, quantity=quantity, price=Decimal(price))


class BillingTests(TestCase):
    def setUp(self):
        self.a = Service.objects.create(name="Svc A", description="a", price=Decimal("100.00"))
        self.b = Service.objects.create(name="Svc B", description="b", price=Decimal("50.00"))
        self.c = Service.objects.create(name="Svc C", description="c", price=Decimal("30.00"))
        self.member = make_customer()
        self.appt = make_booking(self.member, services=[self.a, self.b, self.c])
        self.rows = {row.service_id: row for row in self.appt.appointment_services.all()}

    def complete(self, service, cost=None):
        row = self.rows[service.pk]
        row.status, row.cost = "completed", cost
        row.save()
        return row

    def test_totals_use_the_entered_cost_and_the_parts(self):
        row = self.complete(self.a, Decimal("120.00"))
        add_part(row, quantity=3, price="19.99")
        data = billing.calculate(self.appt)
        self.assertEqual(data["labor_total"], Decimal("120.00"))
        self.assertEqual(data["parts_total"], Decimal("59.97"))
        self.assertEqual(data["total"], Decimal("179.97"))

    def test_blank_cost_bills_the_listed_price(self):
        self.complete(self.b)
        data = billing.calculate(self.appt)
        self.assertEqual(data["labor_total"], Decimal("50.00"))
        self.assertTrue(data["service_lines"][0]["used_list_price"])

    def test_services_that_are_not_completed_are_not_billed(self):
        self.complete(self.a, Decimal("100.00"))
        add_part(self.rows[self.c.pk], price="500.00")  # part on an unfinished service
        data = billing.calculate(self.appt)
        self.assertEqual(data["total"], Decimal("100.00"))
        self.assertEqual({r.service_id for r in data["skipped"]}, {self.b.pk, self.c.pk})

    def test_generate_saves_an_invoice(self):
        row = self.complete(self.a, Decimal("120.00"))
        add_part(row, quantity=2, price="5.50")
        invoice = billing.generate_invoice(self.appt)
        self.assertEqual((invoice.labor_total, invoice.parts_total, invoice.total),
                         (Decimal("120.00"), Decimal("11.00"), Decimal("131.00")))
        self.assertEqual(invoice.payment_status, "unpaid")

    def test_recalculating_updates_the_same_invoice_and_keeps_payment_status(self):
        row = self.complete(self.a, Decimal("120.00"))
        invoice = billing.generate_invoice(self.appt)
        invoice.payment_status = "paid"
        invoice.save()
        row.cost = Decimal("140.00")
        row.save()
        again = billing.generate_invoice(self.appt)
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertEqual((again.pk, again.total, again.payment_status), (invoice.pk, Decimal("140.00"), "paid"))

    def test_nothing_completed_means_no_invoice(self):
        self.assertIsNone(billing.generate_invoice(self.appt))
        self.assertEqual(Invoice.objects.count(), 0)

    def test_database_allows_only_one_invoice_per_appointment(self):
        self.complete(self.a)
        billing.generate_invoice(self.appt)
        with self.assertRaises(_IntegrityError), transaction.atomic():
            Invoice.objects.create(appointment=self.appt, labor_total=0, parts_total=0, total=0)

    def test_out_of_date_detection(self):
        row = self.complete(self.a, Decimal("100.00"))
        invoice = billing.generate_invoice(self.appt)
        self.assertFalse(billing.is_out_of_date(invoice, billing.calculate(self.appt)))
        add_part(row, price="9.00")
        self.assertTrue(billing.is_out_of_date(invoice, billing.calculate(self.appt)))


class StaffInvoiceTests(StaffTestCase):
    def setUp(self):
        self.svc = Service.objects.create(name="Svc A", description="a", price=Decimal("80.00"))
        self.member = make_customer()
        self.appt = make_booking(self.member, services=[self.svc], status="approved")
        self.row = self.appt.appointment_services.get()
        self.url = f"/dashboard/appointments/{self.appt.pk}/invoice/"

    def complete_row(self, cost="80.00"):
        self.row.status, self.row.cost = "completed", Decimal(cost)
        self.row.save()

    def test_requires_staff(self):
        self.assertRedirects(self.client.get(self.url), f"/staff/login/?next={self.url}")
        self.client.post(self.url, {"action": "generate"})
        self.assertEqual(Invoice.objects.count(), 0)

    def test_preview_before_an_invoice_exists_and_viewing_creates_nothing(self):
        self.staff_login()
        self.complete_row()
        response = self.client.get(self.url)
        self.assertContains(response, "No invoice yet")
        self.assertContains(response, "Create invoice")
        self.assertEqual(Invoice.objects.count(), 0)

    def test_generate_creates_the_invoice(self):
        self.staff_login()
        self.complete_row("95.00")
        self.assertRedirects(self.client.post(self.url, {"action": "generate"}), self.url)
        self.assertEqual(Invoice.objects.get().total, Decimal("95.00"))

    def test_generate_with_nothing_completed_is_refused(self):
        self.staff_login()
        response = self.client.post(self.url, {"action": "generate"}, follow=True)
        self.assertContains(response, "Mark at least one service as completed")
        self.assertEqual(Invoice.objects.count(), 0)

    def test_mark_paid_and_unpaid(self):
        self.staff_login()
        self.complete_row()
        self.client.post(self.url, {"action": "generate"})
        self.client.post(self.url, {"action": "mark_paid"})
        self.assertEqual(Invoice.objects.get().payment_status, "paid")
        self.client.post(self.url, {"action": "mark_unpaid"})
        self.assertEqual(Invoice.objects.get().payment_status, "unpaid")

    def test_mark_paid_without_an_invoice_does_nothing(self):
        self.staff_login()
        response = self.client.post(self.url, {"action": "mark_paid"}, follow=True)
        self.assertContains(response, "There is no invoice yet.")

    def test_unknown_action_rejected(self):
        self.staff_login()
        self.assertEqual(self.client.post(self.url, {"action": "explode"}).status_code, 400)

    def test_warns_when_the_invoice_is_out_of_date(self):
        self.staff_login()
        self.complete_row("80.00")
        self.client.post(self.url, {"action": "generate"})
        self.assertNotContains(self.client.get(self.url), "out of date")
        add_part(self.row, price="12.00")
        self.assertContains(self.client.get(self.url), "out of date")


class PartsTests(StaffTestCase):
    def setUp(self):
        self.svc = Service.objects.create(name="Svc A", description="a", price=Decimal("80.00"))
        self.member = make_customer()
        self.appt = make_booking(self.member, services=[self.svc])
        self.row = self.appt.appointment_services.get()
        self.other_row = make_booking(self.member, plate="OTHER1", services=[self.svc]).appointment_services.get()
        self.url = f"/dashboard/appointments/{self.appt.pk}/parts/add/"
        self.staff_login()

    def payload(self, **overrides):
        data = {"appointment_service": self.row.pk, "name": "Oil filter", "quantity": "2", "price": "7.25"}
        data.update(overrides)
        return data

    def test_add_a_part(self):
        response = self.client.post(self.url, self.payload(), follow=True)
        part = PartUsed.objects.get()
        self.assertEqual((part.name, part.quantity, part.price), ("Oil filter", 2, Decimal("7.25")))
        self.assertContains(response, "Oil filter")

    def test_bad_input_is_rejected_with_a_message(self):
        for bad in [{"quantity": "0"}, {"price": "-1"}, {"name": ""}, {"quantity": "abc"}]:
            response = self.client.post(self.url, self.payload(**bad), follow=True)
            self.assertContains(response, "Part not added", msg_prefix=str(bad))
        self.assertEqual(PartUsed.objects.count(), 0)

    def test_cannot_attach_a_part_to_another_appointments_service(self):
        response = self.client.post(self.url, self.payload(appointment_service=self.other_row.pk), follow=True)
        self.assertContains(response, "Part not added")
        self.assertEqual(PartUsed.objects.count(), 0)

    def test_delete_a_part(self):
        part = add_part(self.row)
        response = self.client.post(f"/dashboard/parts/{part.pk}/delete/")
        self.assertRedirects(response, f"/dashboard/appointments/{self.appt.pk}/")
        self.assertEqual(PartUsed.objects.count(), 0)

    def test_get_is_not_allowed(self):
        part = add_part(self.row)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertEqual(self.client.get(f"/dashboard/parts/{part.pk}/delete/").status_code, 405)

    def test_requires_staff(self):
        part = add_part(self.row)
        self.client.post("/staff/logout/")
        self.client.post(self.url, self.payload())
        self.client.post(f"/dashboard/parts/{part.pk}/delete/")
        self.assertEqual(PartUsed.objects.count(), 1)

    def test_manage_page_shows_parts_and_invoice_link(self):
        add_part(self.row, name="Spark plug")
        response = self.client.get(f"/dashboard/appointments/{self.appt.pk}/")
        self.assertContains(response, "Spark plug")
        self.assertContains(response, f"/dashboard/appointments/{self.appt.pk}/invoice/")


class CustomerInvoiceTests(TestCase):
    def setUp(self):
        self.svc = Service.objects.create(name="Svc A", description="a", price=Decimal("80.00"))
        self.me = make_customer()
        self.appt = make_booking(self.me, services=[self.svc], status="completed")
        row = self.appt.appointment_services.get()
        row.status, row.cost = "completed", Decimal("90.00")
        row.save()
        add_part(row, name="Brake pads", quantity=2, price="25.00")
        self.invoice = billing.generate_invoice(self.appt)
        self.url = f"/invoices/{self.invoice.pk}/"

    def login(self, username="sam"):
        self.client.post("/login/", {"username": username, "password": "correct-horse-1"})

    def test_owner_sees_the_invoice(self):
        self.login()
        response = self.client.get(self.url)
        for text in ["Svc A", "Brake pads", "$90.00", "$50.00", "$140.00", "Unpaid"]:
            self.assertContains(response, text)

    def test_other_customers_get_a_404(self):
        make_customer("other")
        self.login("other")
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_guests_are_sent_to_login(self):
        self.assertRedirects(self.client.get(self.url), f"/login/?next={self.url}")

    def test_history_shows_the_total_status_and_link_to_the_owner(self):
        self.login()
        response = self.client.get("/history/")
        self.assertContains(response, "$140.00")
        self.assertContains(response, self.url)

    def test_guest_lookup_shows_the_total_but_no_link(self):
        guest = make_guest()
        appt = make_booking(guest, plate="GUEST1", status="completed", services=[self.svc])
        row = appt.appointment_services.get()
        row.status = "completed"
        row.save()
        invoice = billing.generate_invoice(appt)
        response = self.client.post("/history/", {"plate": "GUEST1", "phone": "555-010-0199"})
        self.assertContains(response, "$80.00")
        self.assertNotContains(response, f"/invoices/{invoice.pk}/")


class ReviewModelTests(TestCase):
    def test_display_name_hides_the_full_last_name(self):
        self.assertEqual(Customer(name="Lucas Tuttle").display_name, "Lucas T.")
        self.assertEqual(Customer(name="Mary Ann Smith").display_name, "Mary S.")
        self.assertEqual(Customer(name="Cher").display_name, "Cher")
        self.assertEqual(Customer(name="").display_name, "Customer")

    def test_stars(self):
        self.assertEqual(Review(rating=4).stars, "\u2605\u2605\u2605\u2605\u2606")

    def test_who_may_review(self):
        cases = [
            ("completed", 0, 1), ("completed", -3, 1), ("approved", -3, 1), ("in_progress", -3, 1),
            ("approved", 3, 0), ("pending", -3, 0), ("denied", -3, 0), ("completed", -3, 1),
        ]
        for i, (status, days, expected) in enumerate(cases):
            customer = make_customer(f"user{i}")
            make_booking(customer, date=future(days), status=status)
            self.assertEqual(customer.reviews_remaining(), expected, (status, days))

    def test_someone_elses_visit_does_not_count(self):
        make_booking(make_customer("a"), date=future(-3), status="completed")
        self.assertEqual(make_customer("b").reviews_remaining(), 0)


class ReviewsPageTests(TestCase):
    def setUp(self):
        self.me = make_customer()
        self.me.name = "Sam Jones"
        self.me.save()

    def login(self):
        self.client.post("/login/", {"username": "sam", "password": "correct-horse-1"})

    def visit(self, plate="ABC123", status="completed", days=-3):
        return make_booking(self.me, plate=plate, date=future(days), status=status)

    def post(self, **overrides):
        data = {"rating": "5", "comment": "Great work."}
        data.update(overrides)
        return self.client.post("/reviews/", data)

    def test_lists_reviews_with_first_name_last_initial_stars_and_average(self):
        Review.objects.create(customer=self.me, rating=5, comment="Fantastic service.")
        other = make_customer("other")
        other.name = "Pat Lee"
        other.save()
        Review.objects.create(customer=other, rating=3, comment="Fine.")
        response = self.client.get("/reviews/")
        for text in ["Sam J.", "Pat L.", "Fantastic service.", "4.0 out of 5", "2 reviews", "\u2605\u2605\u2605\u2605\u2605"]:
            self.assertContains(response, text)
        self.assertNotContains(response, "Jones")
        self.assertNotContains(response, "sam@example.com")

    def test_empty_state(self):
        self.assertContains(self.client.get("/reviews/"), "No reviews yet.")

    def test_guest_sees_login_prompt_and_cannot_post(self):
        self.assertContains(self.client.get("/reviews/"), "to leave a review")
        self.assertRedirects(self.post(), "/login/?next=/reviews/")
        self.assertEqual(Review.objects.count(), 0)

    def test_customer_without_a_past_visit_cannot_review(self):
        self.login()
        self.visit(status="approved", days=5)
        self.assertContains(self.client.get("/reviews/"), "once an appointment has taken place")
        response = self.post()
        self.assertRedirects(response, "/reviews/")
        self.assertEqual(Review.objects.count(), 0)

    def test_eligible_customer_can_post_a_review(self):
        self.login()
        self.visit()
        self.assertContains(self.client.get("/reviews/"), "Post review")
        self.assertRedirects(self.post(rating="4", comment="Quick and fair."), "/reviews/")
        review = Review.objects.get()
        self.assertEqual((review.customer, review.rating, review.comment), (self.me, 4, "Quick and fair."))
        self.assertEqual(review.date, timezone.localdate())

    def test_one_review_per_qualifying_visit(self):
        self.login()
        self.visit()
        self.post()
        self.post(comment="Second try.")
        self.assertEqual(Review.objects.count(), 1)
        self.assertNotContains(self.client.get("/reviews/"), "Post review")
        self.visit(plate="XYZ789", days=-1)
        self.post(comment="Second visit.")
        self.assertEqual(Review.objects.count(), 2)

    def test_invalid_reviews_are_rejected(self):
        self.login()
        self.visit()
        for bad in [{"rating": "0"}, {"rating": "6"}, {"rating": "x"}, {"comment": ""}, {"comment": "   "}, {"comment": "a" * 1001}]:
            response = self.post(**bad)
            self.assertEqual(response.status_code, 200, str(bad)[:40])
        self.assertEqual(Review.objects.count(), 0)

    def test_review_text_is_escaped(self):
        Review.objects.create(customer=self.me, rating=5, comment="<script>alert(1)</script>")
        response = self.client.get("/reviews/")
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>alert(1)")

    def test_navigation_links_to_reviews(self):
        self.assertContains(self.client.get("/"), 'href="/reviews/"')
