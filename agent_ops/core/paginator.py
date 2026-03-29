from django.core.paginator import Page, Paginator


__all__ = (
    "EnhancedPage",
    "EnhancedPaginator",
    "get_paginate_count",
)


class EnhancedPaginator(Paginator):
    default_page_lengths = (25, 50, 100, 250)
    max_per_page = 250

    def __init__(self, object_list, per_page, orphans=None, **kwargs):
        try:
            per_page = int(per_page)
        except (TypeError, ValueError):
            per_page = self.default_page_lengths[1]

        if per_page < 1:
            per_page = self.default_page_lengths[1]

        per_page = min(per_page, self.max_per_page)

        if orphans is None:
            orphans = 5 if per_page <= 50 else 10

        super().__init__(object_list, per_page, orphans=orphans, **kwargs)

    def _get_page(self, *args, **kwargs):
        return EnhancedPage(*args, **kwargs)

    def get_page_lengths(self):
        if self.per_page not in self.default_page_lengths:
            return tuple(sorted({*self.default_page_lengths, self.per_page}))
        return self.default_page_lengths


class EnhancedPage(Page):
    def smart_pages(self):
        if self.paginator.num_pages <= 7:
            return list(self.paginator.page_range)

        current = self.number
        last_page = self.paginator.num_pages
        page_numbers = sorted({1, current - 1, current, current + 1, last_page})
        smart_pages = []

        for page_number in page_numbers:
            if page_number < 1 or page_number > last_page:
                continue

            if smart_pages and smart_pages[-1] is not False and page_number - smart_pages[-1] > 1:
                smart_pages.append(False)

            smart_pages.append(page_number)

        return smart_pages


def get_paginate_count(request):
    if "per_page" in request.GET:
        try:
            per_page = int(request.GET.get("per_page", ""))
        except ValueError:
            per_page = None
        else:
            if per_page > 0:
                return min(per_page, EnhancedPaginator.max_per_page)

    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and hasattr(user, "get_config"):
        return min(
            int(user.get_config().get("ui.page_size", EnhancedPaginator.default_page_lengths[1])),
            EnhancedPaginator.max_per_page,
        )

    return EnhancedPaginator.default_page_lengths[1]
