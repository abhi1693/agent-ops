from collections.abc import Callable


DashboardProvider = Callable[[object], dict]

_dashboard_providers: list[DashboardProvider] = []


def register_dashboard_provider(provider: DashboardProvider) -> None:
    if provider not in _dashboard_providers:
        _dashboard_providers.append(provider)


def build_dashboard_context(request) -> dict:
    stats = []
    panels = []

    for provider in _dashboard_providers:
        contribution = provider(request)
        if not contribution:
            continue
        stats.extend(contribution.get("stats", []))
        panels.extend(contribution.get("panels", []))

    return {
        "stats": stats,
        "dashboard_panels": panels,
    }

