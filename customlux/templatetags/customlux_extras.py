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


@register.filter
def pct(value, places=4):
    """A rate, shown to as many decimals as it actually carries.

    Tax rates go to four places (9.375%, and district add-ons can add a
    fourth), but most rates are round numbers, so trailing zeros are dropped:
    9.3750 -> '9.375', 8.2500 -> '8.25', 30.0000 -> '30'.
    """
    if value is None or value == "":
        return ""
    try:
        rate = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value
    text = f"{rate:.{int(places)}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"
