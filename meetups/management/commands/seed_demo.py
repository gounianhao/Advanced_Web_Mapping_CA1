"""
Create a demo account with an example group of four friends around Dublin.

    docker compose exec web python manage.py seed_demo

Safe to run more than once: it updates the same user, group and friends.
"""

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from django.db import transaction

from meetups.models import Friend, MeetupGroup
from meetups.services import meeting

DEMO_GROUP = "Friday coffee"

# (name, where they are, latitude, longitude)
DEMO_FRIENDS = [
    ("Aoife", "Trinity College", 53.3438, -6.2546),
    ("Cian", "Phibsborough", 53.3590, -6.2730),
    ("Niamh", "Rathmines", 53.3230, -6.2650),
    ("Seán", "Grand Canal Dock", 53.3394, -6.2378),
]


class Command(BaseCommand):
    help = "Create (or reset) the demo user and an example group of four friends."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="demo")
        parser.add_argument("--password", default="meethalfway-demo")

    @transaction.atomic
    def handle(self, *args, **options):
        user, created = get_user_model().objects.get_or_create(username=options["username"])
        user.set_password(options["password"])
        user.save()

        group, _ = MeetupGroup.objects.get_or_create(owner=user, name=DEMO_GROUP)
        for name, place, lat, lon in DEMO_FRIENDS:
            Friend.objects.update_or_create(
                group=group,
                name=name,
                defaults={"place_name": place, "location": Point(lon, lat, srid=4326)},
            )
        meeting.compute_meeting(group)

        action = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(
            f"{action} user '{user.username}' (password: {options['password']}) "
            f"with group '{group.name}' of {group.friends.count()} friends "
            f"(fairness score {group.fairness_score})."
        ))
