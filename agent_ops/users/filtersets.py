from django.db import connections
from django.db.models import Q
import django_filters

from core.filtersets import SearchFilterSet
from users.models import Group, ObjectPermission, Token, User


class UserFilterSet(SearchFilterSet):
    is_staff = django_filters.BooleanFilter(label="Staff")
    is_active = django_filters.BooleanFilter(label="Active")

    class Meta:
        model = User
        fields = ("q", "is_staff", "is_active")

    def search_queryset(self, queryset, value):
        return queryset.filter(
            Q(username__icontains=value)
            | Q(email__icontains=value)
            | Q(display_name__icontains=value)
            | Q(first_name__icontains=value)
            | Q(last_name__icontains=value)
        )


class GroupFilterSet(SearchFilterSet):
    class Meta:
        model = Group
        fields = ("q",)

    def search_queryset(self, queryset, value):
        return queryset.filter(
            Q(name__icontains=value) | Q(description__icontains=value)
        )


class ObjectPermissionFilterSet(SearchFilterSet):
    enabled = django_filters.BooleanFilter(label="Enabled")
    action = django_filters.ChoiceFilter(
        method="filter_action",
        choices=ObjectPermission.ActionChoices.choices,
        label="Action",
    )

    class Meta:
        model = ObjectPermission
        fields = ("q", "enabled", "action")

    def search_queryset(self, queryset, value):
        return queryset.filter(
            Q(name__icontains=value) | Q(description__icontains=value)
        )

    def filter_action(self, queryset, _name, value):
        if not value:
            return queryset
        if connections[queryset.db].vendor == "sqlite":
            matching_ids = [
                permission.pk for permission in queryset if value in permission.actions
            ]
            return queryset.filter(pk__in=matching_ids)
        return queryset.filter(actions__contains=[value])


class TokenFilterSet(SearchFilterSet):
    enabled = django_filters.BooleanFilter(label="Enabled")
    write_enabled = django_filters.BooleanFilter(label="Write enabled")

    class Meta:
        model = Token
        fields = ("q", "enabled", "write_enabled")

    def search_queryset(self, queryset, value):
        return queryset.filter(
            Q(description__icontains=value) | Q(key__icontains=value)
        )
