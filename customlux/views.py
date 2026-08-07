"""CustomLux views — cabinets board at /customlux/.

Access is enforced by the decorators in customlux.access, NOT by panel's
territory scoping. The one exception is `send_lead`, which is reached from
/panel/ and therefore guards on the *panel* user's lead visibility instead.
"""
import re
import secrets

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Count, Max, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from home.models import LeadModel

from .access import OWNER, access_level, customlux_access, customlux_edit, customlux_owner
from .forms import CabinetProjectForm, MemberInviteForm
from .models import CabinetActivity, CabinetMember, CabinetProject, CabinetStage

User = get_user_model()

# Unambiguous alphabet — no O/0 or l/1/I to misread over the phone.
_PW_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"


def _log(project, user, detail):
    CabinetActivity.objects.create(project=project, user=user, detail=detail)


# ── Board ───────────────────────────────────────────────────────────
@customlux_access
def board(request):
    stages = list(CabinetStage.objects.filter(is_active=True))
    projects = (
        CabinetProject.objects.filter(archived=False)
        .select_related("stage", "lead")
    )
    q = (request.GET.get("q") or "").strip()
    if q:
        projects = projects.filter(
            Q(title__icontains=q) | Q(customer_name__icontains=q)
            | Q(email__icontains=q) | Q(phone__icontains=q)
            | Q(address__icontains=q)
        )

    by_stage = {s.id: [] for s in stages}
    for p in projects:
        by_stage.setdefault(p.stage_id, []).append(p)

    columns = [
        {
            "stage": s,
            "projects": by_stage.get(s.id, []),
            "count": len(by_stage.get(s.id, [])),
            "total": sum(
                (p.quoted_amount or 0) for p in by_stage.get(s.id, [])
            ),
        }
        for s in stages
    ]
    return render(request, "customlux/board.html", {
        "columns": columns,
        "q": q,
        "level": request.customlux_level,
        "is_owner": request.customlux_level == OWNER,
        "can_edit": request.customlux_level != "viewer",
        "total_open": projects.count(),
    })


@customlux_access
def project_detail(request, pk):
    project = get_object_or_404(
        CabinetProject.objects.select_related("stage", "lead"), pk=pk
    )
    editable = request.customlux_level != "viewer"

    if request.method == "POST":
        if not editable:
            messages.error(request, "Your access is read-only.")
            return redirect("customlux:project_detail", pk=pk)
        form = CabinetProjectForm(request.POST, instance=project)
        if form.is_valid():
            old_stage = project.stage.label
            obj = form.save()
            if obj.stage.label != old_stage:
                _log(obj, request.user,
                     f"Stage changed from {old_stage} to {obj.stage.label}.")
            else:
                _log(obj, request.user, "Project details updated.")
            messages.success(request, "Saved.")
            return redirect("customlux:project_detail", pk=pk)
    else:
        form = CabinetProjectForm(instance=project)

    return render(request, "customlux/project_detail.html", {
        "project": project,
        "form": form,
        "can_edit": editable,
        "is_owner": request.customlux_level == OWNER,
        "activities": project.activities.select_related("user")[:50],
    })


@customlux_edit
def project_create(request):
    if request.method == "POST":
        form = CabinetProjectForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.created_by = request.user
            obj.order = _next_order(obj.stage_id)
            obj.save()
            _log(obj, request.user, "Project created manually.")
            return redirect("customlux:project_detail", pk=obj.pk)
    else:
        first = CabinetStage.objects.filter(is_active=True).first()
        form = CabinetProjectForm(initial={"stage": first})
    return render(request, "customlux/project_form.html", {
        "form": form, "is_owner": access_level(request.user) == OWNER,
    })


def _next_order(stage_id):
    top = CabinetProject.objects.filter(stage_id=stage_id).aggregate(
        m=Max("order")
    )["m"]
    return (top or 0) + 1


@customlux_edit
@require_POST
def project_move(request, pk):
    """Drag-and-drop endpoint — move a card to another stage."""
    project = get_object_or_404(CabinetProject, pk=pk)
    stage = get_object_or_404(
        CabinetStage, pk=request.POST.get("stage"), is_active=True
    )
    if stage.pk != project.stage_id:
        old = project.stage.label
        project.stage = stage
        project.order = _next_order(stage.pk)
        project.save(update_fields=["stage", "order", "updated_at"])
        _log(project, request.user, f"Moved from {old} to {stage.label}.")
    return JsonResponse({"ok": True, "stage": stage.label})


@customlux_edit
@require_POST
def project_archive(request, pk):
    project = get_object_or_404(CabinetProject, pk=pk)
    project.archived = not project.archived
    project.save(update_fields=["archived", "updated_at"])
    _log(project, request.user,
         "Archived." if project.archived else "Restored to the board.")
    messages.success(
        request, "Archived." if project.archived else "Restored to the board."
    )
    return redirect("customlux:board")


@customlux_access
def archived(request):
    projects = (
        CabinetProject.objects.filter(archived=True)
        .select_related("stage").order_by("-updated_at")
    )
    return render(request, "customlux/archived.html", {
        "projects": projects,
        "is_owner": request.customlux_level == OWNER,
        "can_edit": request.customlux_level != "viewer",
    })


# ── Sending a lead across from /panel/ ──────────────────────────────
@require_POST
def send_lead(request, pk):
    """Copy a panel lead onto the cabinets board.

    Guarded by the *panel* user's own lead visibility (`_lead_queryset`) —
    anyone who can see the lead can hand it to cabinets. The lead itself is
    never modified; everything is snapshotted onto the new CabinetProject.
    """
    if not request.user.is_authenticated:
        return redirect("account:login")
    # Imported lazily: panel.views is heavy and importing it at module load
    # would make customlux depend on panel's import graph.
    from panel.views import _lead_queryset

    lead = get_object_or_404(_lead_queryset(request.user), pk=pk)

    existing = CabinetProject.objects.filter(lead=lead, archived=False).first()
    if existing:
        messages.info(request, "That lead is already on the CustomLux board.")
        return redirect("panel:lead_detail", pk=pk)

    stage = CabinetStage.objects.filter(is_active=True).first()
    if stage is None:
        messages.error(request, "CustomLux has no stages configured yet.")
        return redirect("panel:lead_detail", pk=pk)

    name = f"{lead.first_name} {lead.last_name}".strip()
    project = CabinetProject.objects.create(
        lead=lead,
        title=name or f"Lead #{lead.pk}",
        customer_name=name,
        email=lead.email or "",
        phone=lead.phone or "",
        address=lead.address or "",
        zip_code=lead.zip_code or "",
        source_notes=lead.message or "",
        stage=stage,
        order=_next_order(stage.pk),
        created_by=request.user,
    )
    _log(project, request.user, f"Copied from panel lead #{lead.pk}.")
    messages.success(
        request,
        f"Sent to CustomLux. The lead stays here unchanged — "
        f"the cabinets copy is now on the board.",
    )
    return redirect("panel:lead_detail", pk=pk)


# ── Members (owner only) ────────────────────────────────────────────
def _username_for(email):
    """Derive a valid, unique username. Validator allows [a-zA-Z0-9.+-] only."""
    base = re.sub(r"[^a-zA-Z0-9.+-]", "", email.split("@")[0]) or "member"
    base = base[:100]
    candidate = base
    n = 1
    while User.objects.filter(username=candidate).exists():
        n += 1
        candidate = f"{base}{n}"[:120]
    return candidate


@customlux_owner
def members(request):
    if request.method == "POST":
        form = MemberInviteForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            if CabinetMember.objects.filter(email__iexact=email).exists():
                messages.info(request, f"{email} already has access.")
                return redirect("customlux:members")

            user = User.objects.filter(email__iexact=email).first()
            temp_password = None
            if user is None:
                temp_password = "-".join(
                    "".join(secrets.choice(_PW_ALPHABET) for _ in range(5))
                    for _ in range(4)
                )
                user = User.objects.create_user(
                    username=_username_for(email),
                    email=email,
                    password=temp_password,
                )
            CabinetMember.objects.create(
                email=email, user=user,
                can_edit=form.cleaned_data["can_edit"],
                invited_by=request.user,
            )
            if temp_password:
                messages.success(
                    request,
                    f"Invited {email}. New login created — username "
                    f"“{user.username}”, temporary password “{temp_password}”. "
                    f"This is shown once; pass it along and have them change it.",
                )
            else:
                messages.success(
                    request,
                    f"Invited {email}. They already had a Garage Lions login "
                    f"— they use their existing password.",
                )
            return redirect("customlux:members")
    else:
        form = MemberInviteForm()

    return render(request, "customlux/members.html", {
        "form": form,
        "members": CabinetMember.objects.select_related("user"),
        "is_owner": True,
        "can_edit": True,
        "owner_email": (getattr(request.user, "email", "") or ""),
    })


@customlux_owner
@require_POST
def member_toggle(request, pk):
    member = get_object_or_404(CabinetMember, pk=pk)
    member.is_active = not member.is_active
    member.save(update_fields=["is_active"])
    messages.success(
        request,
        f"{member.email} {'re-enabled' if member.is_active else 'suspended'}.",
    )
    return redirect("customlux:members")


@customlux_owner
@require_POST
def member_remove(request, pk):
    """Revoke board access. Leaves the login account intact on purpose —
    deleting a MyUser would cascade into anything else they touched."""
    member = get_object_or_404(CabinetMember, pk=pk)
    email = member.email
    member.delete()
    messages.success(
        request,
        f"Removed {email} from CustomLux. Their login still exists but can no "
        f"longer open the board.",
    )
    return redirect("customlux:members")
