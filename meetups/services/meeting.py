"""
Finding a group's meeting point and the venues around it.

The API views call these functions; the SQL itself is in spatial.py.
"""

from dataclasses import dataclass

from django.conf import settings
from django.db import transaction

from ..models import Friend, MeetupGroup
from . import spatial
from .fairness import fairness_score


class NotEnoughFriends(Exception):
    """A meeting point needs at least MeetupGroup.MIN_FRIENDS people."""


@dataclass
class GroupArea:
    """Extra facts about the area the group covers (its convex hull)."""

    area_m2: float
    venues_inside: dict


@dataclass
class VenueSearch:
    """The result of a venue search around a meeting point."""

    meeting_point: object  # GEOS Point
    radius_m: int
    categories: list
    search_area: object    # GEOS Polygon: the circle that was searched
    venues: list
    fallback: bool         # True when nothing was in range, so the nearest venues are shown instead


@transaction.atomic
def compute_meeting(group):
    """
    Work out and save the meeting point, each friend's line and distance to
    it, the group's hull and the fairness score. Returns a GroupArea.
    """
    # Lock the group so two calculations at the same time can't mix their results.
    MeetupGroup.objects.select_for_update().get(pk=group.pk)

    friends = list(group.friends.all())
    if len(friends) < MeetupGroup.MIN_FRIENDS:
        raise NotEnoughFriends(
            f"Add at least {MeetupGroup.MIN_FRIENDS} friends to find a meeting point."
        )

    point = spatial.meeting_point(group.pk)

    lines = spatial.lines_to_point(group.pk, point)
    for friend in friends:
        friend.line_to_meeting, friend.distance_m = lines.get(friend.pk, (None, None))
    Friend.objects.bulk_update(friends, ["line_to_meeting", "distance_m"])

    hull, area_m2 = spatial.group_hull(group.pk)

    group.meeting_point = point
    group.hull = hull
    group.fairness_score = fairness_score(f.distance_m for f in friends if f.distance_m is not None)
    group.save(update_fields=["meeting_point", "hull", "fairness_score", "updated_at"])

    # Runs after the save because it joins against the saved hull.
    return GroupArea(area_m2=area_m2, venues_inside=spatial.venues_in_hull(group.pk))


@transaction.atomic
def clear_meeting(group):
    """Remove the saved results, e.g. when fewer than two friends are left."""
    group.friends.update(line_to_meeting=None, distance_m=None)
    group.meeting_point = None
    group.hull = None
    group.fairness_score = None
    group.save(update_fields=["meeting_point", "hull", "fairness_score", "updated_at"])


def refresh_meeting(group):
    """Keep the saved results up to date after a friend is added, moved or removed."""
    if group.friends.count() >= MeetupGroup.MIN_FRIENDS:
        compute_meeting(group)
    else:
        clear_meeting(group)


def search_venues(point, radius_m, categories):
    """
    Venues within radius_m of the point, nearest first. If there are none
    (e.g. the middle of the group is in Dublin Bay) the nearest few are
    returned instead and .fallback is True.
    """
    venues = spatial.venues_within(point, radius_m, categories, settings.VENUE_SEARCH_LIMIT)
    fallback = not venues
    if fallback:
        venues = spatial.nearest_venues(point, categories, settings.VENUE_FALLBACK_COUNT)
    return VenueSearch(
        meeting_point=point,
        radius_m=radius_m,
        categories=sorted(categories),
        search_area=spatial.search_area(point, radius_m),
        venues=venues,
        fallback=fallback,
    )


def search_fair_venues(group, radius_m, categories):
    """The same venues as search_venues, ranked by how fair each one is for the group."""
    search = search_venues(group.meeting_point, radius_m, categories)
    search.venues = spatial.rank_by_fairness(
        group.pk, group.meeting_point, [venue.pk for venue in search.venues]
    )
    return search
