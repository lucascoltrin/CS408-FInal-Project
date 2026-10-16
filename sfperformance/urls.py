from django.urls import include, path

from . import views

urlpatterns = [
    path("api/health", views.health, name="health"),
    path("", include("shop.urls")),
]
