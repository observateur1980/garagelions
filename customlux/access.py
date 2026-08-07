"""Who may touch /customlux/.

Three tiers, checked in this order:

  owner   settings.CUSTOMLUX_OWNER_EMAIL, or any superuser (break-glass so a
          typo in that setting can never lock everybody out). May invite and
          remove members, and edit everything.
  editor  an active CabinetMember with can_edit=True.
  viewer  an active CabinetMember with can_edit=False. Read-only.

This is intentionally *not* wired into panel's ProjectManager/role scoping —
the whole point of the board is that it is separate from CRM territory rules.
"""
from functools import wraps

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from .models import CabinetMember

OWNER, EDITOR, VIEWER = "owner", "editor", "viewer"


def _owner_email():
    return (getattr(settings, "CUSTOMLUX_OWNER_EMAIL", "") or "").strip().lower()


def access_level(user):
    """Return OWNER / EDITOR / VIEWER, or None if the user has no access."""
    if not user or not user.is_authenticated or not user.is_active:
        return None
    email = (user.email or "").strip().lower()
    if user.is_superuser or (email and email == _owner_email()):
        return OWNER
    member = (
        CabinetMember.objects.filter(is_active=True)
        .filter(user=user)
        .first()
    )
    if member is None and email:
        # Invited by address before the account existed / was linked.
        member = CabinetMember.objects.filter(
            is_active=True, email__iexact=email,
        ).first()
        if member is not None and member.user_id is None:
            member.user = user
            member.save(update_fields=["user"])
    if member is None:
        return None
    return EDITOR if member.can_edit else VIEWER


def is_owner(user):
    return access_level(user) == OWNER


def can_edit(user):
    return access_level(user) in (OWNER, EDITOR)


def customlux_access(view):
    """Any access level. Anonymous users get the normal login redirect."""
    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        level = access_level(request.user)
        if level is None:
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            raise PermissionDenied("You do not have access to CustomLux.")
        request.customlux_level = level
        return view(request, *args, **kwargs)
    return _wrapped


def customlux_edit(view):
    """Write endpoints — owner or editor only."""
    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        level = access_level(request.user)
        if level is None:
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            raise PermissionDenied("You do not have access to CustomLux.")
        if level == VIEWER:
            raise PermissionDenied("Your CustomLux access is read-only.")
        request.customlux_level = level
        return view(request, *args, **kwargs)
    return _wrapped


def customlux_owner(view):
    """Member management — owner only."""
    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        if not is_owner(request.user):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            raise PermissionDenied("Only the CustomLux owner can do that.")
        request.customlux_level = OWNER
        return view(request, *args, **kwargs)
    return _wrapped
