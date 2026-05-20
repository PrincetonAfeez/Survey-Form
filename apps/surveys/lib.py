""" Shared helpers with no dependency on forms, display, or repositories """

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from .models import Choice


def trim_decimal(value) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, Decimal):
        value = value.normalize()
        text = format(value, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    return str(value)


def rating_value(value: Choice | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value.label)
    except (InvalidOperation, TypeError):
        return Decimal(value.order)
