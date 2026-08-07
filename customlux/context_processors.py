"""Expose CustomLux access to templates outside the app.

Used by the panel sidebar to show the CustomLux link to the owner only. Kept
as a context processor rather than a hardcoded email in the template so
`CUSTOMLUX_OWNER_EMAIL` stays the single place the owner is defined.
"""
from django.conf import settings


def customlux_owner(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"is_customlux_owner": False}
    owner = (getattr(settings, "CUSTOMLUX_OWNER_EMAIL", "") or "").strip().lower()
    email = (user.email or "").strip().lower()
    return {"is_customlux_owner": bool(owner) and email == owner}
