"""The HTML pages: map, register, log in, log out and the health check."""

from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

pytestmark = pytest.mark.django_db


def test_map_page_invites_visitors_to_register(client):
    response = client.get("/")
    assert response.status_code == 200
    page = response.content.decode()
    assert "Register" in page
    assert "meetup.js" not in page  # the planner is only for logged-in users


def test_map_page_shows_the_planner_when_logged_in(client, user):
    client.force_login(user)
    page = client.get("/").content.decode()
    assert 'id="group-select"' in page
    assert "meetup.js" in page
    assert "csrfToken" in page


def test_register_creates_an_account_and_logs_in(client):
    response = client.post("/accounts/register/", {
        "username": "niamh", "password1": "a-strong-pass-9831", "password2": "a-strong-pass-9831",
    })
    assert response.status_code == 302
    assert response["Location"] == "/"
    user = get_user_model().objects.get(username="niamh")
    assert int(client.session["_auth_user_id"]) == user.pk


def test_register_shows_errors(client):
    response = client.post("/accounts/register/", {
        "username": "niamh", "password1": "a-strong-pass-9831", "password2": "something-else-9831",
    })
    assert response.status_code == 200
    assert "is-invalid" in response.content.decode()
    assert not get_user_model().objects.filter(username="niamh").exists()


def test_log_in_and_out(client, user):
    assert client.get("/accounts/login/").status_code == 200
    response = client.post("/accounts/login/", {"username": "aoife", "password": "test-pass-123"})
    assert response.status_code == 302
    assert "_auth_user_id" in client.session

    assert client.get("/accounts/logout/").status_code == 405  # only POST logs out
    assert client.post("/accounts/logout/").status_code == 302
    assert "_auth_user_id" not in client.session


def test_health_check(client):
    response = client.get("/healthz/")
    assert response.status_code == 200
    assert response.content == b"ok"


def test_explain_venue_search_prints_a_query_plan():
    out = StringIO()
    call_command("explain_venue_search", stdout=out)
    assert "Scan" in out.getvalue()
