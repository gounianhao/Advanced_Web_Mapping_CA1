"""Query-string filters for the REST API (django-filter)."""

import django_filters

from .models import Venue


class VenueFilter(django_filters.FilterSet):
    """?category=cafe&category=pub (any of) and ?name=… (contains, ignoring case)."""

    category = django_filters.MultipleChoiceFilter(choices=Venue.Category.choices)
    name = django_filters.CharFilter(lookup_expr="icontains", max_length=100)

    class Meta:
        model = Venue
        fields = ["category", "name"]
