"""Keep CustomLux-only accounts inside /customlux/.

Without this, an invited cabinets contractor could simply type /panel/ and get
in: every panel view is `@login_required` and nothing more. Worse, panel's
`_filter_by_sp()` falls back to `sales_point__isnull=True` for a user with no
ProjectManager, so records with no sales point would be visible to them.

"CustomLux-only" means: authenticated, not staff/superuser, has no
ProjectManager (so no job in the CRM), and holds a CabinetMember row or is the
configured owner email. Those users get bounced to their board. Everyone else
is untouched.

The row is what confines them, *not* their current access level — a suspended
member's level is None, and if that lifted the confinement then Suspend would
hand them the CRM instead of taking the board away.
"""
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse

from account.models import ProjectManager

# Only the internal tools are off limits. Deliberately a blocklist, not an
# allowlist: these accounts are still ordinary visitors to garagelions.com and
# must be able to browse the public site while logged in.
_BLOCKED_PREFIXES = (
    "/panel/",
    "/taskboard/",
    "/admin/",
)


class CustomLuxScopeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and not user.is_staff
            and not user.is_superuser
            and request.path.startswith(_BLOCKED_PREFIXES)
        ):
            # Imported here so the middleware module stays importable during
            # migrations, and to keep the DB hit off unblocked paths.
            from .access import OWNER, access_level
            from .models import CabinetMember

            # The owner is the business owner — they get the panel too, and the
            # sidebar shows them a CustomLux link. Only *invited* members are
            # confined to the board.
            if access_level(user) == OWNER:
                return self.get_response(request)
            if ProjectManager.objects.filter(user=user).exists():
                return self.get_response(request)

            email = (user.email or "").strip().lower()
            match = Q(user=user)
            if email:
                match |= Q(email__iexact=email)
            if CabinetMember.objects.filter(match).exists():
                return redirect(reverse("customlux:board"))
        return self.get_response(request)
