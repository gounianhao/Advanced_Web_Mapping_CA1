"""Top-level URL routes for Meet Halfway."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("meetups.api_urls")),
    path("", include("meetups.urls")),
]
