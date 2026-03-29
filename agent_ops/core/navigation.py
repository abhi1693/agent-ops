from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from django.urls import reverse_lazy


NavigationProvider = Callable[[object], object]

_navigation_providers: list[NavigationProvider] = []


@dataclass
class MenuItem:
    link: str
    link_text: str
    icon_class: str | None = None
    add_link: str | None = None
    add_button_label: str | None = None
    active_links: Sequence[str] = ()
    permissions: Sequence[str] = ()
    auth_required: bool = False
    staff_only: bool = False
    _url: str | None = field(init=False, default=None, repr=False)
    _add_url: str | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        if self.link:
            self._url = reverse_lazy(self.link)
        if self.add_link:
            self._add_url = reverse_lazy(self.add_link)

    @property
    def url(self) -> str | None:
        return self._url

    @property
    def add_url(self) -> str | None:
        return self._add_url

    def is_visible(self, user) -> bool:
        if self.auth_required and not user.is_authenticated:
            return False
        if self.staff_only and not (user.is_staff or user.is_superuser):
            return False
        if self.permissions and not user.has_perms(self.permissions):
            return False
        return True

    def is_active(self, current_url_name: str | None) -> bool:
        active_links = self.active_links or (self.link.rsplit(":", 1)[-1],)
        return current_url_name in active_links


@dataclass
class MenuGroup:
    label: str
    items: Sequence[MenuItem]


@dataclass
class Menu:
    label: str
    icon_class: str
    groups: Sequence[MenuGroup]
    permissions: Sequence[str] = ()
    auth_required: bool = False
    staff_only: bool = False

    def is_visible(self, user) -> bool:
        if self.auth_required and not user.is_authenticated:
            return False
        if self.staff_only and not (user.is_staff or user.is_superuser):
            return False
        if self.permissions and not user.has_perms(self.permissions):
            return False
        return True


def register_navigation_provider(provider: NavigationProvider) -> None:
    if provider not in _navigation_providers:
        _navigation_providers.append(provider)


def build_navigation(request) -> list[dict]:
    current_url_name = getattr(getattr(request, "resolver_match", None), "url_name", None)
    user = request.user
    nav_items: list[dict] = []

    for provider in _navigation_providers:
        contribution = provider(request)
        if not contribution:
            continue

        menus = contribution if isinstance(contribution, Sequence) else (contribution,)
        for menu in menus:
            if not menu.is_visible(user):
                continue

            visible_groups = []
            menu_is_active = False

            for group in menu.groups:
                visible_items = []
                for item in group.items:
                    if not item.is_visible(user):
                        continue

                    item_is_active = item.is_active(current_url_name)
                    visible_items.append(
                        {
                            "label": item.link_text,
                            "icon_class": item.icon_class,
                            "url": item.url,
                            "add_url": item.add_url,
                            "add_button_label": item.add_button_label,
                            "active": item_is_active,
                        }
                    )
                    menu_is_active = menu_is_active or item_is_active

                if visible_items:
                    visible_groups.append(
                        {
                            "label": group.label,
                            "items": visible_items,
                        }
                    )

            if visible_groups:
                nav_items.append(
                    {
                        "label": menu.label,
                        "icon_class": menu.icon_class,
                        "groups": visible_groups,
                        "active": menu_is_active,
                    }
                )

    return nav_items
