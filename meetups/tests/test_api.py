"""The REST API: logins, ownership, validation and the meeting endpoints."""

import pytest
import requests
from django.contrib.gis.geos import Point
from rest_framework.test import APIClient

from meetups.models import MeetupGroup

from .helpers import CENTRE, geojson, shifted

pytestmark = pytest.mark.django_db


def add_friend(api, group, name, point):
    return api.post("/api/friends/", {"group": group.pk, "name": name, "location": geojson(point)})


def compute(api, group):
    response = api.post(f"/api/groups/{group.pk}/compute/")
    assert response.status_code == 200
    return response.json()


# --- logins and ownership ---------------------------------------------------------
def test_venues_are_public():
    assert APIClient().get("/api/venues/").status_code == 200


@pytest.mark.parametrize("url", ["/api/groups/", "/api/friends/", "/api/geocode/?q=Spire"])
def test_user_data_needs_a_login(url):
    assert APIClient().get(url).status_code == 403


def test_users_only_see_their_own_groups(api, make_group, other_user):
    mine = make_group(CENTRE, name="Mine")
    theirs = make_group(CENTRE, owner=other_user, name="Theirs")

    names = [group["name"] for group in api.get("/api/groups/").json()]
    assert names == ["Mine"]
    assert api.get(f"/api/groups/{theirs.pk}/").status_code == 404
    assert api.delete(f"/api/groups/{theirs.pk}/").status_code == 404
    assert api.get(f"/api/groups/{mine.pk}/").status_code == 200


def test_new_group_belongs_to_the_logged_in_user(api, user):
    response = api.post("/api/groups/", {"name": "Lunch"})
    assert response.status_code == 201
    assert response.json()["search_radius_m"] == 300
    assert MeetupGroup.objects.get(pk=response.json()["id"]).owner == user


def test_cannot_add_a_friend_to_someone_elses_group(api, make_group, other_user):
    theirs = make_group(owner=other_user)
    response = add_friend(api, theirs, "Sneaky", CENTRE)
    assert response.status_code == 400
    assert "group" in response.json()


# --- validation ---------------------------------------------------------------------
@pytest.mark.parametrize("radius", [20, 5000])
def test_group_radius_must_be_50_to_2000_metres(api, radius):
    response = api.post("/api/groups/", {"name": "Lunch", "search_radius_m": radius})
    assert response.status_code == 400
    assert "search_radius_m" in response.json()


def test_friend_must_be_in_dublin(api, make_group):
    group = make_group()
    cork = Point(-8.4756, 51.8985, srid=4326)
    response = add_friend(api, group, "Siobhán", cork)
    assert response.status_code == 400
    assert "Greater Dublin" in response.json()["location"][0]


def test_friend_location_must_be_a_point(api, make_group):
    response = api.post("/api/friends/", {
        "group": make_group().pk, "name": "Pól",
        "location": {"type": "LineString", "coordinates": [[-6.26, 53.34], [-6.25, 53.35]]},
    })
    assert response.status_code == 400
    assert "location" in response.json()


def test_friend_names_are_unique_in_a_group(api, make_group):
    group = make_group(CENTRE)  # already has "Friend 1"
    response = add_friend(api, group, "friend 1", shifted(CENTRE, north_m=500))
    assert response.status_code == 400
    assert "name" in response.json()


def test_a_group_has_at_most_15_friends(api, make_group):
    group = make_group(*[shifted(CENTRE, north_m=50 * n) for n in range(MeetupGroup.MAX_FRIENDS)])
    response = add_friend(api, group, "One too many", CENTRE)
    assert response.status_code == 400
    assert "at most 15" in response.json()["group"][0]


def test_friend_cannot_move_to_another_group(api, make_group):
    group, other = make_group(CENTRE), make_group(name="Other")
    friend = group.friends.get()
    response = api.patch(f"/api/friends/{friend.pk}/", {"group": other.pk})
    assert response.status_code == 400


# --- meeting point ------------------------------------------------------------------
def test_adding_and_removing_friends_keeps_the_meeting_point_up_to_date(api, make_group):
    group = make_group()
    add_friend(api, group, "Aoife", shifted(CENTRE, east_m=-1000))
    response = add_friend(api, group, "Cian", shifted(CENTRE, east_m=1000))
    assert response.status_code == 201
    assert response.json()["distance_m"] == pytest.approx(1000, abs=3)

    detail = api.get(f"/api/groups/{group.pk}/").json()
    assert detail["meeting_point"]["type"] == "Point"
    assert detail["fairness_label"] == "Fair"
    assert len(detail["friends"]) == 2

    api.delete(f"/api/friends/{response.json()['id']}/")
    detail = api.get(f"/api/groups/{group.pk}/").json()
    assert detail["meeting_point"] is None
    assert detail["friends"][0]["distance_m"] is None


def test_moving_a_friend_moves_the_meeting_point(api, make_group):
    group = make_group(shifted(CENTRE, east_m=-1000), shifted(CENTRE, east_m=1000))
    before = compute(api, group)["group"]["meeting_point"]

    friend = group.friends.first()
    api.patch(f"/api/friends/{friend.pk}/", {"location": geojson(shifted(CENTRE, north_m=2000))})

    after = api.get(f"/api/groups/{group.pk}/").json()["meeting_point"]
    assert after != before


def test_compute_needs_two_friends(api, make_group):
    response = api.post(f"/api/groups/{make_group(CENTRE).pk}/compute/")
    assert response.status_code == 400
    assert "at least 2 friends" in response.json()["detail"]


def test_compute_returns_the_whole_result(api, make_group, make_venue):
    group = make_group(CENTRE, shifted(CENTRE, east_m=1000), shifted(CENTRE, north_m=1000))
    make_venue(shifted(CENTRE, north_m=330, east_m=330))

    data = compute(api, group)

    assert data["group"]["hull"]["type"] == "Polygon"
    assert data["group"]["fairness_score"] is not None
    assert all(friend["line_to_meeting"]["type"] == "LineString" for friend in data["group"]["friends"])
    assert data["area"]["venues_inside"]["cafe"] == 1
    assert data["venues"]["search_area"]["type"] == "Polygon"
    assert data["venues"]["venues"]["type"] == "FeatureCollection"
    assert data["venues"]["count"] == 1


# --- venue searches -------------------------------------------------------------------
def test_venue_search_needs_a_meeting_point(api, make_group):
    response = api.get(f"/api/groups/{make_group(CENTRE).pk}/venues/")
    assert response.status_code == 400
    assert "no meeting point" in response.json()["detail"]


@pytest.mark.parametrize("query", ["radius=10", "radius=5000", "radius=abc", "category=nightclub"])
def test_venue_search_options_are_checked(api, make_group, query):
    group = make_group(CENTRE, shifted(CENTRE, north_m=500))
    compute(api, group)
    response = api.get(f"/api/groups/{group.pk}/venues/?{query}")
    assert response.status_code == 400


def test_venue_search_reports_the_fallback(api, make_group, make_venue):
    group = make_group(shifted(CENTRE, east_m=-1000), shifted(CENTRE, east_m=1000))
    compute(api, group)
    make_venue(shifted(CENTRE, north_m=800))

    nearby = api.get(f"/api/groups/{group.pk}/venues/?radius=300").json()
    assert nearby["fallback"] is True
    assert nearby["count"] == 1

    wider = api.get(f"/api/groups/{group.pk}/venues/?radius=1000").json()
    assert wider["fallback"] is False
    assert wider["radius_m"] == 1000
    feature = wider["venues"]["features"][0]
    assert feature["properties"]["distance_m"] == pytest.approx(800, abs=3)


def test_fair_venues_are_ranked_by_fairness(api, make_group, make_venue):
    group = make_group(shifted(CENTRE, east_m=-1000), shifted(CENTRE, east_m=1000))
    compute(api, group)
    make_venue(shifted(CENTRE, east_m=200), name="Lopsided")
    make_venue(CENTRE, name="Middle")

    data = api.get(f"/api/groups/{group.pk}/fair-venues/?category=cafe").json()

    names = [feature["properties"]["name"] for feature in data["venues"]["features"]]
    assert names == ["Middle", "Lopsided"]
    assert data["venues"]["features"][0]["properties"]["fairness_label"] == "Fair"


# --- address search -------------------------------------------------------------------
class FakeNominatim:
    """Stands in for requests.get so the tests never call the real Nominatim."""

    def __init__(self, places=None, error=None):
        self.places = places or []
        self.error = error
        self.calls = []

    def __call__(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        if self.error:
            raise self.error
        return self

    def raise_for_status(self):
        pass

    def json(self):
        return self.places


def test_geocode_returns_places_in_dublin_and_caches_them(api, monkeypatch):
    fake = FakeNominatim(places=[
        {"display_name": "Heuston Station, Dublin", "lat": "53.3464", "lon": "-6.2923", "type": "station"},
        {"display_name": "Somewhere in Cork", "lat": "51.8985", "lon": "-8.4756", "type": "city"},
    ])
    monkeypatch.setattr("meetups.services.geocoding.requests.get", fake)

    first = api.get("/api/geocode/", {"q": "Heuston Station"})
    second = api.get("/api/geocode/", {"q": "heuston   station"})

    assert first.status_code == 200
    assert first.json()["results"] == [
        {"name": "Heuston Station, Dublin", "lat": 53.3464, "lon": -6.2923, "type": "station"},
    ]
    assert second.json()["results"] == first.json()["results"]
    assert len(fake.calls) == 1  # the second search came from the cache
    assert "MeetHalfway" in fake.calls[0]["headers"]["User-Agent"]
    assert fake.calls[0]["params"]["bounded"] == 1


def test_geocode_query_must_be_at_least_3_characters(api):
    assert api.get("/api/geocode/?q=ab").status_code == 400


def test_geocode_reports_when_nominatim_is_down(api, monkeypatch):
    monkeypatch.setattr("meetups.services.geocoding.requests.get",
                        FakeNominatim(error=requests.ConnectionError("no network")))
    response = api.get("/api/geocode/?q=Spire")
    assert response.status_code == 503


# --- documentation ----------------------------------------------------------------------
def test_api_schema_and_docs_load():
    client = APIClient()
    assert client.get("/api/schema/").status_code == 200
    assert client.get("/api/docs/").status_code == 200
