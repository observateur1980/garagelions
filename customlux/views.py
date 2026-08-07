"""CustomLux views — cabinets board at /customlux/.

Access is enforced by the decorators in customlux.access, NOT by panel's
territory scoping. The one exception is `send_lead`, which is reached from
/panel/ and therefore guards on the *panel* user's lead visibility instead.
"""
import re
import secrets
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Count, Max, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from account.models import ProjectManager

from .access import OWNER, access_level, customlux_access, customlux_edit, customlux_owner
from .forms import (
    CabinetEstimateForm, CabinetPaymentForm, CabinetProjectForm,
    CabinetSettingsForm, CabinetStageFormSet, CabinetTodoForm,
    ChangeOrderForm, CustomerPaymentForm, MemberInviteForm, NewStageForm,
)
from .models import (
    CabinetActivity, CabinetChangeOrder, CabinetCustomerPayment, CabinetEstimate,
    CabinetMember, CabinetPayment, CabinetProject, CabinetSettings, CabinetStage,
    CabinetTodo,
)

User = get_user_model()

# Unambiguous alphabet — no O/0 or l/1/I to misread over the phone.
_PW_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"


def _log(project, user, detail):
    CabinetActivity.objects.create(project=project, user=user, detail=detail)


# Fields worth naming in the history, and how to render them.
_TRACKED = [
    ("stage", "Stage", "stage"),
    ("quoted_amount", "Deal total", "money"),
    ("tax_amount", "Sales tax", "money"),
    ("commission_rate", "Commission rate", "pct"),
    ("collected_by", "Who the customer pays", "collect"),
    ("deposit_percent", "Deposit", "pct"),
    ("customer_name", "Customer", "text"),
    ("phone", "Phone", "text"),
    ("email", "Email", "text"),
    ("address", "Address", "text"),
    ("zip_code", "ZIP", "text"),
    ("title", "Title", "text"),
    ("measure_date", "Measure date", "date"),
    ("install_date", "Install date", "date"),
    ("notes", "Notes", "long"),
]


def _collect_label(value):
    return "Garage Lions" if value == CabinetSettings.COLLECTED_GARAGELIONS else "CustomLux"


def _fmt(value, kind):
    if kind == "collect":
        # Blank means "inherit the board default" — not "nothing".
        if not value:
            return f"board default ({_collect_label(CabinetSettings.get().default_collected_by)})"
        return _collect_label(value)
    if value in (None, ""):
        return "empty"
    if kind == "money":
        return f"${value:,.2f}"
    if kind == "pct":
        return f"{value:g}%"
    if kind == "stage":
        return str(value)
    if kind == "date":
        return value.strftime("%b %-d, %Y")
    return str(value)


def _snapshot(project):
    return {f: getattr(project, f) for f, _, _ in _TRACKED}


def _log_changes(project, user, before):
    """Write one history line per field the user actually changed."""
    after = _snapshot(project)
    changed = 0
    for field, label, kind in _TRACKED:
        old, new = before.get(field), after.get(field)
        if old == new:
            continue
        changed += 1
        if kind == "long":
            _log(project, user, f"{label} updated.")
        else:
            _log(project, user,
                 f"{label}: {_fmt(old, kind)} → {_fmt(new, kind)}")
    return changed


def _parent_template(request):
    """Which shell to render inside.

    Anyone who can use /panel/ gets the panel chrome, so CustomLux looks and
    navigates exactly like Leads. Invited members are barred from /panel/ by
    the middleware, so showing them its sidebar would be all dead links —
    they get the standalone shell.
    """
    user = request.user
    if user.is_staff or user.is_superuser:
        return "panel/base.html"
    if access_level(user) == OWNER:
        return "panel/base.html"
    if ProjectManager.objects.filter(user=user).exists():
        return "panel/base.html"
    return "customlux/shell.html"


# ── Board ───────────────────────────────────────────────────────────
@customlux_access
def board(request):
    """Mirrors panel's lead_list: table/grid/board views, stage chips, search."""
    stages = list(CabinetStage.objects.filter(is_active=True))
    projects = (
        CabinetProject.objects.filter(archived=False)
        .select_related("stage", "lead")
        .prefetch_related("payments", "change_orders", "customer_payments")
    )

    q = (request.GET.get("q") or "").strip()
    if q:
        projects = projects.filter(
            Q(title__icontains=q) | Q(customer_name__icontains=q)
            | Q(email__icontains=q) | Q(phone__icontains=q)
            | Q(address__icontains=q) | Q(zip_code__icontains=q)
        )

    stage_code = (request.GET.get("stage") or "").strip()
    if stage_code:
        projects = projects.filter(stage__code=stage_code)

    # The chosen view sticks. Picking one stores it on the session, and every
    # later visit without an explicit ?view= reuses it — otherwise navigating
    # back from a project would silently drop you into the table again.
    view_mode = request.GET.get("view")
    if view_mode in ("table", "grid", "board"):
        request.session["customlux_view"] = view_mode
    else:
        view_mode = request.session.get("customlux_view") or "table"
        if view_mode not in ("table", "grid", "board"):
            view_mode = "table"

    # Counts for the chips reflect the search but not the stage filter —
    # otherwise every chip but the active one would read zero.
    counted = CabinetProject.objects.filter(archived=False)
    if q:
        counted = counted.filter(
            Q(title__icontains=q) | Q(customer_name__icontains=q)
            | Q(email__icontains=q) | Q(phone__icontains=q)
            | Q(address__icontains=q) | Q(zip_code__icontains=q)
        )
    per_stage = dict(
        counted.values_list("stage_id").annotate(n=Count("id")).values_list(
            "stage_id", "n"
        )
    )
    quick_filters = [
        {"code": s.code, "label": s.label, "color": s.color,
         "count": per_stage.get(s.id, 0)}
        for s in stages
    ]

    ctx = {
        "parent_template": _parent_template(request),
        "q": q,
        "stage_code": stage_code,
        "stages": stages,
        "quick_filters": quick_filters,
        "view_mode": view_mode,
        "total_open": projects.count(),
        "level": request.customlux_level,
        "is_owner": request.customlux_level == OWNER,
        "is_customlux_owner": request.customlux_level == OWNER,
        "can_edit": request.customlux_level != "viewer",
    }

    if view_mode == "board":
        by_stage = {}
        for p in projects.order_by("order", "-created_at"):
            by_stage.setdefault(p.stage_id, []).append(p)
        ctx["columns"] = [
            {
                "stage": s,
                "projects": by_stage.get(s.id, []),
                "count": len(by_stage.get(s.id, [])),
                "total": sum((p.quoted_amount or 0) for p in by_stage.get(s.id, [])),
                "commission": sum(
                    (p.commission_amount or 0) for p in by_stage.get(s.id, [])
                ),
            }
            for s in stages
        ]
    else:
        paginator = Paginator(projects.order_by("-created_at"), 24)
        ctx["page_obj"] = paginator.get_page(request.GET.get("page"))

    # Totals across everything the current filters match, not just this page.
    ctx["sum_total"] = sum((p.current_total or 0) for p in projects)
    ctx["sum_commission"] = sum((p.commission_amount or 0) for p in projects)
    ctx["sum_to_collect"] = sum(
        (p.settlement_outstanding or 0) for p in projects
        if not p.we_collect and (p.settlement_outstanding or 0) > 0
    )
    ctx["sum_to_pay"] = sum(
        (p.settlement_outstanding or 0) for p in projects
        if p.we_collect and (p.settlement_outstanding or 0) > 0
    )
    ctx["conf"] = CabinetSettings.get()

    return render(request, "customlux/board.html", ctx)


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
        before = _snapshot(
            CabinetProject.objects.select_related("stage").get(pk=project.pk)
        )
        form = CabinetProjectForm(request.POST, instance=project)
        if form.is_valid():
            obj = form.save()
            n = _log_changes(obj, request.user, before)
            messages.success(
                request,
                f"Saved — {n} change{'' if n == 1 else 's'} recorded."
                if n else "Nothing changed.",
            )
            return redirect("customlux:project_detail", pk=pk)
    else:
        form = CabinetProjectForm(instance=project)

    return render(request, "customlux/project_detail.html", {
        "parent_template": _parent_template(request),
        "is_customlux_owner": request.customlux_level == OWNER,
        "project": project,
        "form": form,
        "conf": CabinetSettings.get(),
        "todo_form": CabinetTodoForm(),
        "estimate_form": CabinetEstimateForm(),
        "todos": project.todos.all(),
        "open_todos": project.todos.filter(is_completed=False).count(),
        "estimates": project.estimates.select_related("uploaded_by"),
        "payment_form": CabinetPaymentForm(),
        "payments": project.payments.select_related("recorded_by"),
        "customer_payment_form": CustomerPaymentForm(),
        "customer_payments": project.customer_payments.select_related("recorded_by"),
        "change_order_form": ChangeOrderForm(),
        "change_orders": project.change_orders.select_related("created_by"),
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
        "parent_template": _parent_template(request),
        "form": form,
        "conf": CabinetSettings.get(),
        "is_owner": access_level(request.user) == OWNER,
        "is_customlux_owner": access_level(request.user) == OWNER,
        "can_edit": True,
    })


# ── To-dos ──────────────────────────────────────────────────────────
@customlux_edit
@require_POST
def todo_add(request, pk):
    project = get_object_or_404(CabinetProject, pk=pk)
    form = CabinetTodoForm(request.POST)
    if form.is_valid():
        todo = form.save(commit=False)
        todo.project = project
        todo.created_by = request.user
        todo.save()
        _log(project, request.user, f"To-do added: {todo.title}")
    else:
        messages.error(request, "Give the task a title.")
    return redirect("customlux:project_detail", pk=pk)


@customlux_edit
@require_POST
def todo_toggle(request, pk, todo_pk):
    todo = get_object_or_404(CabinetTodo, pk=todo_pk, project_id=pk)
    todo.is_completed = not todo.is_completed
    todo.completed_at = timezone.now() if todo.is_completed else None
    todo.save(update_fields=["is_completed", "completed_at"])
    _log(todo.project, request.user,
         f"To-do {'completed' if todo.is_completed else 'reopened'}: {todo.title}")
    return redirect("customlux:project_detail", pk=pk)


@customlux_edit
@require_POST
def todo_delete(request, pk, todo_pk):
    todo = get_object_or_404(CabinetTodo, pk=todo_pk, project_id=pk)
    title = todo.title
    project = todo.project
    todo.delete()
    _log(project, request.user, f"To-do deleted: {title}")
    return redirect("customlux:project_detail", pk=pk)


# ── Customer payments ───────────────────────────────────────────────
@customlux_edit
@require_POST
def customer_payment_add(request, pk):
    project = get_object_or_404(CabinetProject, pk=pk)
    form = CustomerPaymentForm(request.POST)
    if form.is_valid():
        pay = form.save(commit=False)
        pay.project = project
        pay.recorded_by = request.user
        pay.save()
        bits = [
            f"Customer paid ${pay.amount:,.2f}"
            + (" (deposit)" if pay.is_deposit else "")
        ]
        if pay.method:
            bits.append(pay.get_method_display().lower())
        if pay.reference:
            bits.append(f"ref {pay.reference}")
        _log(project, request.user,
             " · ".join(bits) + f" on {pay.received_on:%b %-d, %Y}")

        balance = project.customer_balance
        if balance is not None and balance <= 0:
            _log(project, request.user, "Customer paid in full.")
            messages.success(request, "Recorded — the customer is paid in full.")
        elif balance is not None:
            messages.success(
                request, f"Recorded. ${balance:,.2f} still due from the customer."
            )
        else:
            messages.success(request, "Recorded.")
    else:
        for errs in form.errors.values():
            for e in errs:
                messages.error(request, e)
    return redirect("customlux:project_detail", pk=pk)


@customlux_edit
@require_POST
def customer_payment_delete(request, pk, pay_pk):
    pay = get_object_or_404(CabinetCustomerPayment, pk=pay_pk, project_id=pk)
    amount, when, project = pay.amount, pay.received_on, pay.project
    pay.delete()
    _log(project, request.user,
         f"Customer payment removed: ${amount:,.2f} of {when:%b %-d, %Y}")
    messages.success(request, "Payment removed.")
    return redirect("customlux:project_detail", pk=pk)


# ── Change orders ───────────────────────────────────────────────────
@customlux_edit
@require_POST
def change_order_add(request, pk):
    """Adjust the contract mid-job. Everything downstream recomputes."""
    project = get_object_or_404(CabinetProject, pk=pk)
    form = ChangeOrderForm(request.POST)
    if form.is_valid():
        before_total = project.current_total
        before_comm = project.commission_amount
        co = form.save(commit=False)
        co.project = project
        co.created_by = request.user
        co.save()
        project.refresh_from_db()

        verb = "increase" if co.is_increase else "reduction"
        _log(project, request.user,
             f"Change order ({verb}): {co.description} — ${co.amount:+,.2f}. "
             f"Deal total ${before_total or 0:,.2f} → ${project.current_total:,.2f}, "
             f"commission ${before_comm or 0:,.2f} → ${project.commission_amount or 0:,.2f}")
        messages.success(
            request,
            f"Change order added. Deal total is now "
            f"${project.current_total:,.2f} and your commission "
            f"${project.commission_amount or 0:,.2f}.",
        )
    else:
        for errs in form.errors.values():
            for e in errs:
                messages.error(request, e)
    return redirect("customlux:project_detail", pk=pk)


@customlux_edit
@require_POST
def change_order_delete(request, pk, co_pk):
    co = get_object_or_404(CabinetChangeOrder, pk=co_pk, project_id=pk)
    desc, amount, project = co.description, co.amount, co.project
    co.delete()
    project.refresh_from_db()
    _log(project, request.user,
         f"Change order removed: {desc} (${amount:+,.2f}). "
         f"Deal total back to ${project.current_total or 0:,.2f}")
    messages.success(request, "Change order removed.")
    return redirect("customlux:project_detail", pk=pk)


# ── Commission payments ─────────────────────────────────────────────
@customlux_edit
@require_POST
def payment_add(request, pk):
    """Register commission actually received from CustomLux."""
    project = get_object_or_404(CabinetProject, pk=pk)
    form = CabinetPaymentForm(request.POST)
    if form.is_valid():
        pay = form.save(commit=False)
        pay.project = project
        pay.recorded_by = request.user
        pay.save()
        verb = ("Received ${:,.2f} from CustomLux" if pay.direction == CabinetPayment.DIR_IN
                else "Sent ${:,.2f} to CustomLux").format(pay.amount)
        bits = [verb]
        if pay.method:
            bits.append(pay.get_method_display().lower())
        if pay.reference:
            bits.append(f"ref {pay.reference}")
        _log(project, request.user,
             " · ".join(bits) + f" on {pay.received_on:%b %-d, %Y}")

        outstanding = project.settlement_outstanding
        if outstanding is not None and outstanding <= 0:
            _log(project, request.user, "Deal fully settled.")
            messages.success(request, "Recorded — this deal is fully settled.")
        elif outstanding is not None:
            owed = "to collect" if not project.we_collect else "to pay out"
            messages.success(
                request, f"Recorded. ${outstanding:,.2f} still {owed}."
            )
        else:
            messages.success(request, "Payment recorded.")
    else:
        for errs in form.errors.values():
            for e in errs:
                messages.error(request, e)
    return redirect("customlux:project_detail", pk=pk)


@customlux_edit
@require_POST
def payment_delete(request, pk, pay_pk):
    pay = get_object_or_404(CabinetPayment, pk=pay_pk, project_id=pk)
    amount, when = pay.amount, pay.received_on
    project = pay.project
    pay.delete()
    _log(project, request.user,
         f"Payment removed: ${amount:,.2f} of {when:%b %-d, %Y}")
    messages.success(request, "Payment removed.")
    return redirect("customlux:project_detail", pk=pk)


# ── Estimates (files only) ──────────────────────────────────────────
@customlux_edit
@require_POST
def estimate_upload(request, pk):
    project = get_object_or_404(CabinetProject, pk=pk)
    form = CabinetEstimateForm(request.POST, request.FILES)
    if form.is_valid():
        est = form.save(commit=False)
        est.project = project
        est.uploaded_by = request.user
        est.save()
        _log(project, request.user, f"Estimate uploaded: {est.filename}")
        messages.success(request, "Estimate uploaded.")
    else:
        for err in form.errors.get("file", []) or form.errors.get("label", []):
            messages.error(request, err)
        if not form.errors:
            messages.error(request, "Choose a file to upload.")
    return redirect("customlux:project_detail", pk=pk)


@customlux_edit
@require_POST
def estimate_delete(request, pk, est_pk):
    est = get_object_or_404(CabinetEstimate, pk=est_pk, project_id=pk)
    name = est.filename
    # Drop the file from disk too, not just the row.
    est.file.delete(save=False)
    est.delete()
    _log(est.project, request.user, f"Estimate removed: {name}")
    messages.success(request, f"Removed {name}.")
    return redirect("customlux:project_detail", pk=pk)


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
        "parent_template": _parent_template(request),
        "is_customlux_owner": request.customlux_level == OWNER,
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
        "parent_template": _parent_template(request),
        "is_customlux_owner": True,
        "form": form,
        "members": CabinetMember.objects.select_related("user"),
        "is_owner": True,
        "can_edit": True,
        "owner_email": (getattr(request.user, "email", "") or ""),
    })


# ── Settings (owner only) ───────────────────────────────────────────
@customlux_owner
def board_settings(request):
    """Commission split and stage management, without going near Django admin."""
    conf = CabinetSettings.get()
    action = request.POST.get("action") if request.method == "POST" else None

    settings_form = CabinetSettingsForm(instance=conf)
    stage_formset = CabinetStageFormSet(queryset=CabinetStage.objects.all())
    new_stage_form = NewStageForm(initial={"color": "#6b7280", "order": _next_stage_order()})

    if action == "settings":
        settings_form = CabinetSettingsForm(request.POST, instance=conf)
        if settings_form.is_valid():
            old, old_basis = conf.commission_rate, conf.commission_basis
            obj = settings_form.save()
            if obj.commission_basis != old_basis:
                messages.success(
                    request,
                    f"Commission is now calculated as a "
                    f"{obj.get_commission_basis_display().lower()}.",
                )
            elif obj.commission_rate != old:
                messages.success(
                    request,
                    f"Commission rate changed from {old:g}% to "
                    f"{obj.commission_rate:g}%. Deals with their own rate are "
                    f"unaffected.",
                )
            else:
                messages.success(request, "Settings saved.")
            return redirect("customlux:settings")

    elif action == "stages":
        stage_formset = CabinetStageFormSet(request.POST)
        if stage_formset.is_valid():
            blocked = []
            for form in stage_formset.deleted_forms:
                stage = form.instance
                # PROTECT on CabinetProject.stage would raise; check first so
                # the owner gets an explanation instead of a 500.
                if stage.pk and stage.projects.exists():
                    blocked.append(stage.label)
            if blocked:
                messages.error(
                    request,
                    "Can't delete " + ", ".join(blocked) +
                    " — projects are still in that stage. Move them first, or "
                    "untick Active to hide the stage instead.",
                )
            else:
                stage_formset.save()
                messages.success(request, "Stages updated.")
            return redirect("customlux:settings")

    elif action == "new_stage":
        new_stage_form = NewStageForm(request.POST)
        if new_stage_form.is_valid():
            stage = new_stage_form.save()
            messages.success(request, f"Added stage “{stage.label}”.")
            return redirect("customlux:settings")

    # Worked example, run through the real model properties so the page can
    # never drift from the maths the board actually uses.
    sample = CabinetProject(
        stage_id=CabinetStage.objects.values_list("pk", flat=True).first(),
        quoted_amount=Decimal("5200"), tax_amount=Decimal("0"),
    )

    return render(request, "customlux/settings.html", {
        "parent_template": _parent_template(request),
        "example": {
            "total": sample.quoted_amount,
            "their_price": sample.subcontractor_price,
            "commission": sample.commission_amount,
            "share_pct": (
                sample.commission_amount / sample.quoted_amount * 100
            ).quantize(Decimal("0.01")),
        },
        "is_customlux_owner": True,
        "is_owner": True,
        "can_edit": True,
        "conf": conf,
        "settings_form": settings_form,
        "stage_formset": stage_formset,
        "new_stage_form": new_stage_form,
        "stage_usage": {
            s.pk: s.projects.count() for s in CabinetStage.objects.all()
        },
    })


def _next_stage_order():
    top = CabinetStage.objects.aggregate(m=Max("order"))["m"]
    return (top or 0) + 10


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
