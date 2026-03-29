import django_filters


__all__ = ("SearchFilterSet",)


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
