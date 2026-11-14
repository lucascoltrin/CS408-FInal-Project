from getpass import getpass

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError

from shop.models import Employee


class Command(BaseCommand):
    help = "Create a staff login (or reset its password with --reset-password). Run this on the server."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--name", default="", help="Display name (defaults to the username).")
        parser.add_argument("--password", help="Optional. Leave it out to be prompted, which keeps it out of shell history.")
        parser.add_argument("--reset-password", action="store_true", help="Change the password of an existing login.")

    def handle(self, *args, **options):
        username = options["username"].strip()
        existing = Employee.objects.filter(username=username).first()
        if options["reset_password"] and not existing:
            raise CommandError(f'No staff login named "{username}".')
        if existing and not options["reset_password"]:
            raise CommandError(f'"{username}" already exists. Use --reset-password to change its password.')

        password = options["password"] or self._prompt()
        if len(password) < 8:
            raise CommandError("Password must be at least 8 characters.")

        if existing:
            existing.password_hash = make_password(password)
            existing.save(update_fields=["password_hash"])
            self.stdout.write(self.style.SUCCESS(f'Password updated for "{username}".'))
        else:
            Employee.objects.create(
                name=options["name"] or username, username=username, password_hash=make_password(password),
            )
            self.stdout.write(self.style.SUCCESS(f'Created staff login "{username}".'))

    def _prompt(self):
        first = getpass("Password: ")
        if first != getpass("Password (again): "):
            raise CommandError("Passwords did not match.")
        return first
