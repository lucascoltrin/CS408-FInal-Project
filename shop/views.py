from django.shortcuts import redirect, render
from django.urls import reverse

from .forms import ContactForm


def home(request):
    return render(request, "shop/home.html")


def about(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect(f"{reverse('about')}?sent=1")
    else:
        form = ContactForm()
    return render(request, "shop/about.html", {"form": form, "sent": request.GET.get("sent") == "1"})
