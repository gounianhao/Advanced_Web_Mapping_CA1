import django.contrib.gis.db.models.fields
import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Venue",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("osm_id", models.CharField(max_length=32, unique=True)),
                ("name", models.CharField(max_length=200)),
                (
                    "category",
                    models.CharField(
                        choices=[("cafe", "Café"), ("restaurant", "Restaurant"), ("pub", "Pub")],
                        db_index=True,
                        max_length=20,
                    ),
                ),
                ("cuisine", models.CharField(blank=True, max_length=100)),
                ("address", models.CharField(blank=True, max_length=255)),
                ("opening_hours", models.CharField(blank=True, max_length=255)),
                ("website", models.URLField(blank=True, max_length=300)),
                ("location", django.contrib.gis.db.models.fields.PointField(srid=4326)),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="MeetupGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                (
                    "search_radius_m",
                    models.PositiveIntegerField(
                        default=300,
                        validators=[
                            django.core.validators.MinValueValidator(50),
                            django.core.validators.MaxValueValidator(2000),
                        ],
                        verbose_name="search radius (m)",
                    ),
                ),
                ("meeting_point", django.contrib.gis.db.models.fields.PointField(blank=True, null=True, srid=4326)),
                (
                    "hull",
                    django.contrib.gis.db.models.fields.PolygonField(
                        blank=True, null=True, srid=4326, verbose_name="group area"
                    ),
                ),
                ("fairness_score", models.FloatField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="meetup_groups",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
        migrations.CreateModel(
            name="Friend",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=60)),
                ("place_name", models.CharField(blank=True, max_length=255)),
                ("location", django.contrib.gis.db.models.fields.PointField(srid=4326)),
                (
                    "line_to_meeting",
                    django.contrib.gis.db.models.fields.LineStringField(blank=True, null=True, srid=4326),
                ),
                ("distance_m", models.FloatField(blank=True, null=True, verbose_name="distance (m)")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "group",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="friends",
                        to="meetups.meetupgroup",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at", "id"],
                "constraints": [
                    models.UniqueConstraint(fields=("group", "name"), name="unique_friend_name_per_group"),
                ],
            },
        ),
    ]
