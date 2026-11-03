from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Register, log in and log out (uses Django's built-in user model)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
