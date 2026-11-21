"""Invoice math. An invoice bills the services marked completed, plus the parts used on them."""
from decimal import Decimal

from .models import Invoice

CENTS = Decimal("0.01")


def calculate(appointment):
    """Work out what an appointment costs from its service rows and parts. Nothing is saved."""
    rows = appointment.appointment_services.select_related("service").prefetch_related("parts").order_by("id")
    service_lines, part_lines, skipped = [], [], []
    labor = parts_total = Decimal("0.00")
    for row in rows:
        if row.status != "completed":
            skipped.append(row)
            continue
        # Use the cost the owner entered; if none was entered, bill the listed price.
        amount = row.cost if row.cost is not None else row.service.price
        service_lines.append({"row": row, "amount": amount, "used_list_price": row.cost is None})
        labor += amount
        for part in row.parts.all():
            line_total = (part.price * part.quantity).quantize(CENTS)
            part_lines.append({"part": part, "service": row.service, "line_total": line_total})
            parts_total += line_total
    labor, parts_total = labor.quantize(CENTS), parts_total.quantize(CENTS)
    return {
        "service_lines": service_lines, "part_lines": part_lines, "skipped": skipped,
        "labor_total": labor, "parts_total": parts_total, "total": labor + parts_total,
    }


def generate_invoice(appointment):
    """Create the invoice, or recalculate it if one exists (payment status is kept).
    Returns None when nothing has been completed yet."""
    data = calculate(appointment)
    if not data["service_lines"]:
        return None
    invoice, _ = Invoice.objects.update_or_create(
        appointment=appointment,
        defaults={"labor_total": data["labor_total"], "parts_total": data["parts_total"], "total": data["total"]},
    )
    return invoice


def is_out_of_date(invoice, data):
    """True when services or parts changed after the invoice was generated."""
    return (invoice.labor_total, invoice.parts_total, invoice.total) != (
        data["labor_total"], data["parts_total"], data["total"],
    )
