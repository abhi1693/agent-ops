import django_filters
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model
from django.db.models import Q

from core.models import ObjectChange


__all__ = ("ObjectChangeFilterSet", "SearchFilterSet")


class SearchFilterSet(django_filters.FilterSet):
    q = django_filters.CharFilter(
        method="search",
        label="Quick search",
    )

    def search(self, queryset, _name, value):
        value = (value or "").strip()
        if not value:
            return queryset

        return self.search_queryset(queryset, value)

    def search_queryset(self, queryset, value):
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement search_queryset()"
        )


class ObjectChangeFilterSet(SearchFilterSet):
    action = django_filters.ChoiceFilter(
        choices=ObjectChange.ActionChoices.choices,
        label="Action",
    )
    user = django_filters.ModelChoiceFilter(
        queryset=get_user_model().objects.order_by("username"),
        label="User",
    )
    changed_object_type = django_filters.ModelChoiceFilter(
        queryset=ContentType.objects.order_by("app_label", "model"),
        label="Object type",
    )
    request_id = django_filters.UUIDFilter(label="Request ID")

    class Meta:
        model = ObjectChange
        fields = ("q", "action", "user", "changed_object_type", "request_id")

    def search_queryset(self, queryset, value):
        filters = (
            Q(object_repr__icontains=value)
            | Q(user_name__icontains=value)
        )
        if value.isdigit():
            filters |= Q(changed_object_id=int(value)) | Q(related_object_id=int(value))
        return queryset.filter(filters)
