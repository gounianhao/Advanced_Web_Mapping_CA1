"""
Shared test fixtures.

Run the tests inside the web container (pytest creates and removes its own
test database, so the real data is never touched):

    docker compose exec web pytest
"""

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from meetups.models import Friend, MeetupGroup, Venue


@pytest.fixture(autouse=True)
def test_cache(settings):
    """A private in-memory cache for each test, so tests never share cached results."""
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    cache.clear()


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user("aoife", password="test-pass-123")


@pytest.fixture
def other_user(django_user_model):
    return django_user_model.objects.create_user("cian", password="test-pass-456")


@pytest.fixture
def api(user):
    """An API client logged in as `user`."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def make_group(user):
    """make_group(point, point, ...) -> a group of the given user with one friend per point."""

    def make(*points, owner=None, name="Test group"):
        group = MeetupGroup.objects.create(owner=owner or user, name=name)
        for number, point in enumerate(points, start=1):
            Friend.objects.create(group=group, name=f"Friend {number}", location=point)
        return group

    return make


@pytest.fixture
def make_venue():
    """make_venue(point, category="cafe", name=None) -> a saved venue."""
    counter = iter(range(1, 10_000))

    def make(point, category=Venue.Category.CAFE, name=None):
        number = next(counter)
        return Venue.objects.create(
            osm_id=f"node/{number}", name=name or f"Venue {number}", category=category, location=point,
        )

    return make
