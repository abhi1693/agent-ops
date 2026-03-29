from django import template


register = template.Library()


@register.filter
def form_field(form, name):
    try:
        return form[name]
    except KeyError:
        return None
