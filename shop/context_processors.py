from .models import Customer

# Edit these values to change the shop details shown in the header and footer.
SHOP_INFO = {
    "name": "SF Performance",
    "tagline": "Performance modifications and repairs",
    "hours": "By appointment",
    "location": "Location shared when you book",
}


def shop_info(request):
    return {"shop": SHOP_INFO}


def customer_session(request):
    """Expose the logged-in customer and cart size to every template."""
    customer = None
    customer_id = request.session.get("customer_id")
    if customer_id:
        customer = Customer.objects.filter(pk=customer_id).first()
        if customer is None:  # account was deleted; drop the stale session
            request.session.flush()
    cart = request.session.get("cart", []) if customer else []
    return {"current_customer": customer, "cart_count": len(cart)}
