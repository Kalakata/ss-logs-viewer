from django import template

register = template.Library()


@register.filter
def default_if_none(value, default=''):
    if value is None:
        return default
    return value
