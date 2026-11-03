"""The PostGIS queries in meetups/services/spatial.py and the meeting calculation."""

import pytest
from django.contrib.gis.geos import Point

from meetups.models import Venue
from meetups.services import meeting, spatial

from .helpers import CENTRE, metres_between, shifted

pytestmark = pytest.mark.django_db


# --- meeting point, lines and fairness -----------------------------------------
def test_meeting_point_is_the_centre_of_the_group(make_group):
    group = make_group(
        shifted(CENTRE, north_m=1000), shifted(CENTRE, north_m=-1000),
        shifted(CENTRE, east_m=1500), shifted(CENTRE, east_m=-1500),
    )
    point = spatial.meeting_point(group.pk)
    assert point.srid == 4326
    assert metres_between(point, CENTRE) < 1


def test_two_friends_meet_in_the_middle_with_a_score_of_100(make_group):
    group = make_group(shifted(CENTRE, east_m=-1000), shifted(CENTRE, east_m=1000))
    area = meeting.compute_meeting(group)

    group.refresh_from_db()
    assert metres_between(group.meeting_point, CENTRE) < 1
    distances = list(group.friends.values_list("distance_m", flat=True))
    assert distances == [pytest.approx(1000, abs=3)] * 2
    assert group.fairness_score >= 99.9
    # Two friends make a line, which has no area.
    assert group.hull is None
    assert area.area_m2 == 0


def test_friends_at_the_same_spot_do_not_break_anything(make_group):
    group = make_group(CENTRE, CENTRE)
    meeting.compute_meeting(group)

    group.refresh_from_db()
    assert metres_between(group.meeting_point, CENTRE) < 0.01
    assert list(group.friends.values_list("distance_m", flat=True)) == [0, 0]
    assert group.fairness_score == 100
    assert group.hull is None


def test_lines_run_from_each_friend_to_the_meeting_point(make_group):
    start = shifted(CENTRE, north_m=800)
    group = make_group(start, shifted(CENTRE, north_m=-800))
    meeting.compute_meeting(group)

    friend = group.friends.get(name="Friend 1")
    first, last = friend.line_to_meeting.coords
    assert first == pytest.approx(start.coords)
    assert metres_between(Point(last, srid=4326), CENTRE) < 1


def test_one_friend_far_away_makes_the_group_unfair(make_group):
    # Three friends near the Spire and one 4 km west: trips of about 1, 1, 1 and 3 km.
    group = make_group(
        CENTRE, shifted(CENTRE, north_m=1), shifted(CENTRE, north_m=-1), shifted(CENTRE, east_m=-4000),
    )
    meeting.compute_meeting(group)
    group.refresh_from_db()
    assert group.fairness_score == pytest.approx(42.3, abs=0.5)


def test_compute_needs_two_friends(make_group):
    with pytest.raises(meeting.NotEnoughFriends):
        meeting.compute_meeting(make_group(CENTRE))


# --- the group's hull -----------------------------------------------------------
def test_three_friends_make_a_polygon_with_an_area(make_group, make_venue):
    group = make_group(CENTRE, shifted(CENTRE, east_m=1000), shifted(CENTRE, north_m=1000))
    make_venue(shifted(CENTRE, north_m=200, east_m=200))                        # inside
    make_venue(shifted(CENTRE, north_m=-500), category=Venue.Category.PUB)     # outside

    area = meeting.compute_meeting(group)

    group.refresh_from_db()
    assert group.hull.geom_type == "Polygon"
    assert area.area_m2 == pytest.approx(500_000, rel=0.01)  # right triangle, 1 km x 1 km / 2
    assert area.venues_inside == {"cafe": 1, "restaurant": 0, "pub": 0}


def test_friends_in_a_straight_line_have_no_hull(make_group):
    group = make_group(CENTRE, shifted(CENTRE, north_m=500), shifted(CENTRE, north_m=1000))
    meeting.compute_meeting(group)
    group.refresh_from_db()
    assert group.hull is None


# --- venue searches -------------------------------------------------------------
def test_radius_search_finds_venues_in_range_nearest_first(make_venue):
    near = make_venue(shifted(CENTRE, north_m=100))
    further = make_venue(shifted(CENTRE, north_m=250))
    make_venue(shifted(CENTRE, north_m=400))                                     # too far
    make_venue(shifted(CENTRE, north_m=150), category=Venue.Category.PUB)       # not a café

    search = meeting.search_venues(CENTRE, 300, ["cafe"])

    assert [venue.pk for venue in search.venues] == [near.pk, further.pk]
    assert search.venues[0].distance_m == pytest.approx(100, abs=2)
    assert search.venues[1].distance_m == pytest.approx(250, abs=2)
    assert search.fallback is False


def test_radius_search_can_include_several_categories(make_venue):
    make_venue(shifted(CENTRE, north_m=100))
    make_venue(shifted(CENTRE, north_m=150), category=Venue.Category.PUB)
    search = meeting.search_venues(CENTRE, 300, ["cafe", "pub"])
    assert len(search.venues) == 2


def test_search_area_is_a_circle_of_the_radius():
    circle = spatial.search_area(CENTRE, 300)
    assert circle.geom_type == "Polygon"
    assert circle.contains(CENTRE)
    edge = Point(circle.exterior_ring.coords[0], srid=4326)
    assert metres_between(edge, CENTRE) == pytest.approx(300, abs=1)


def test_meeting_point_in_dublin_bay_falls_back_to_the_nearest_venues(make_group, make_venue):
    # Howth and Dalkey: the middle of the two is out in Dublin Bay.
    group = make_group(Point(-6.0640, 53.3786, srid=4326), Point(-6.1000, 53.2775, srid=4326))
    on_land = [
        (-6.2120, 53.3330),  # Sandymount
        (-6.1350, 53.2945),  # Dún Laoghaire
        (-6.2000, 53.3640),  # Clontarf
        (-6.0650, 53.3870),  # Howth village
        (-6.1780, 53.3010),  # Blackrock
        (-6.2270, 53.3420),  # Ringsend
        (-6.2603, 53.3498),  # city centre
    ]
    for lon, lat in on_land:
        make_venue(Point(lon, lat, srid=4326))
    meeting.compute_meeting(group)
    group.refresh_from_db()

    search = meeting.search_venues(group.meeting_point, 300, ["cafe"])

    assert search.fallback is True
    assert len(search.venues) == 5
    distances = [venue.distance_m for venue in search.venues]
    assert distances == sorted(distances)
    assert distances[0] > 300


def test_fairest_venue_is_the_one_everyone_travels_equally_to(make_group, make_venue):
    group = make_group(shifted(CENTRE, east_m=-1000), shifted(CENTRE, east_m=1000))
    meeting.compute_meeting(group)
    group.refresh_from_db()
    lopsided = make_venue(shifted(CENTRE, east_m=200), name="Lopsided")
    middle = make_venue(CENTRE, name="Middle")

    search = meeting.search_fair_venues(group, 300, ["cafe"])

    assert [venue.pk for venue in search.venues] == [middle.pk, lopsided.pk]
    assert search.venues[0].fairness_score == pytest.approx(100, abs=0.5)
    # Trips of 800 m and 1200 m: mean 1000, spread 200 -> 80.
    assert search.venues[1].fairness_score == pytest.approx(80, abs=0.5)
    assert search.venues[1].longest_trip_m == pytest.approx(1200, abs=3)
