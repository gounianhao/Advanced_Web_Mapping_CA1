"""Top-level URL routes for Meet Halfway."""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerSplitView

from meetups.views import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    # API documentation: OpenAPI schema and Swagger UI. The "split" view loads
    # its script from a URL instead of inline, so it works with the CSP header.
    path("api/schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path("api/docs/", SpectacularSwaggerSplitView.as_view(url_name="api-schema"), name="api-docs"),
    # Log in / out links of the browsable API
    path("api-auth/", include("rest_framework.urls")),
    path("api/", include("meetups.api_urls")),
    path("healthz/", health, name="health"),
    path("", include("meetups.urls")),
]
