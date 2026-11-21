from django.urls import path

from . import staff_views, views

urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("services/", views.services, name="services"),
    path("book/", views.book, name="book"),
    path("book/confirmed/", views.book_confirmation, name="book_confirmation"),
    path("history/", views.history, name="history"),
    path("appointments/<int:pk>/edit/", views.appointment_edit, name="appointment_edit"),
    path("staff/login/", staff_views.staff_login, name="staff_login"),
    path("staff/logout/", staff_views.staff_logout, name="staff_logout"),
    path("dashboard/", staff_views.dashboard, name="dashboard"),
    path("dashboard/appointments/<int:pk>/", staff_views.dashboard_appointment, name="dashboard_appointment"),
    path("dashboard/appointments/<int:pk>/action/", staff_views.dashboard_action, name="dashboard_action"),
    path("dashboard/appointments/<int:pk>/delete/", staff_views.dashboard_delete, name="dashboard_delete"),
    path("reviews/", views.reviews, name="reviews"),
    path("invoices/<int:pk>/", views.invoice_detail, name="invoice_detail"),
    path("dashboard/appointments/<int:pk>/parts/add/", staff_views.dashboard_part_add, name="dashboard_part_add"),
    path("dashboard/parts/<int:pk>/delete/", staff_views.dashboard_part_delete, name="dashboard_part_delete"),
    path("dashboard/appointments/<int:pk>/invoice/", staff_views.dashboard_invoice, name="dashboard_invoice"),
    path("register/", views.register, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("cart/", views.cart, name="cart"),
    path("cart/add/", views.cart_add, name="cart_add"),
    path("cart/remove/", views.cart_remove, name="cart_remove"),
]
