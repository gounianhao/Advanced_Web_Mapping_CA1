"""URL routes for the Meet Halfway pages."""

from django.urls import path

from . import views

app_name = "meetups"

urlpatterns = [
    path("", views.MapView.as_view(), name="map"),
]
