from django.apps import AppConfig


class MeetupsConfig(AppConfig):
    """The Meet Halfway app: groups of friends, venues and meeting points."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "meetups"
    verbose_name = "Meet Halfway"
