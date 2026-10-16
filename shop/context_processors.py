# Edit these values to change the shop details shown in the header and footer.
SHOP_INFO = {
    "name": "SF Performance",
    "tagline": "Performance modifications and repairs",
    "hours": "7 days a week, 9am - 6pm. Appointment only.",
    "location": "Based out of Boise, Idaho. Exact location will be provided after booking.",
}


def shop_info(request):
    return {"shop": SHOP_INFO}
