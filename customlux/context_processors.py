"""Expose CustomLux access to templates outside the app.

Drives the CustomLux link in the panel sidebar: the owner
(`CUSTOMLUX_OWNER_EMAIL`) and any superuser see it, nobody else does. Kept as
a context processor rather than a hardcoded email in the template so the
setting stays the single place the owner is defined.
"""
from django.conf import settings


def customlux_owner(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"is_customlux_owner": False}
    if user.is_superuser:
        return {"is_customlux_owner": True}
    owner = (getattr(settings, "CUSTOMLUX_OWNER_EMAIL", "") or "").strip().lower()
    email = (user.email or "").strip().lower()
    return {"is_customlux_owner": bool(owner) and email == owner}
