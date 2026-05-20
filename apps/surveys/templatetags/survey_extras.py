from apps.surveys.display import format_answer_value
from apps.surveys.display import trim_decimal as _trim_decimal
from django import template

register = template.Library()


@register.filter
def trim_decimal(value):
    return _trim_decimal(value)


@register.filter
def duration(value):
    if value is None:
        return "N/A"
    try:
        value = int(value)
    except (TypeError, ValueError):
        return "N/A"
    minutes, seconds = divmod(value, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


@register.filter
def answer_display(answer):
    return format_answer_value(answer)
