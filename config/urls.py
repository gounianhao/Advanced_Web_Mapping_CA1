"""Top-level URL routes for Meet Halfway."""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    # API documentation: OpenAPI schema and Swagger UI
    path("api/schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="api-schema"), name="api-docs"),
    # Log in / out pages of the browsable API (also used before trying the API in Swagger)
    path("api-auth/", include("rest_framework.urls")),
    path("api/", include("meetups.api_urls")),
    path("", include("meetups.urls")),
]
