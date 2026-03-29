from django import template

from core.navigation import build_navigation


register = template.Library()


@register.inclusion_tag("core/inc/navigation_menu.html", takes_context=True)
def nav(context):
    request = context.get("request")
    if request is None:
        return {"nav_items": []}
    return {"nav_items": build_navigation(request)}
