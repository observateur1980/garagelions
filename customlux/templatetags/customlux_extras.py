"""Money formatting for CustomLux templates.

Deliberately self-contained rather than using `humanize`'s `intcomma`:
`django.contrib.humanize` is not part of this app's own settings changes, and
CustomLux must not depend on anything outside itself to render correctly.
`USE_THOUSAND_SEPARATOR` is off site-wide, so `floatformat` alone gives
"6000.00" while the flash messages say "$6,000.00" — this closes that gap.
"""
from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def money(value, places=2):
    """1234.5 -> '1,234.50'. Blank for None so templates can fall back."""
    if value is None or value == "":
        return ""
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value
    return f"{amount:,.{int(places)}f}"


@register.filter
def money0(value):
    """Same, rounded to whole dollars — for compact card and column labels."""
    return money(value, 0)
