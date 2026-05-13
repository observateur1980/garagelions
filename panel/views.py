from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.db.models import Sum, Q, Case, When, IntegerField, Value, Subquery, OuterRef, CharField
from django.utils import timezone
from decimal import Decimal, InvalidOperation as DecimalInvalid
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.cache import never_cache

from django.core.paginator import Paginator
from django.db.models import Count

from account.models import ProjectManager
from home.models import LeadModel, LeadActivity, LeadTodo, LeadFollowUp, SalesPoint, LeadStatus
from home.forms import LeadUpdateForm, ManualLeadForm
from .models import (
    Customer, Project, Part, PartCategory, SalesPointPartCategory,
    Unit, SalesPointUnit, SalesPointPart,
    Estimate, EstimateItem, EstimateComponent,
    EstimateTemplate, EstimateTemplateItem,
    EstimatePackage,
    Invoice, InvoiceItem,
    Transaction, TaskList, Task,
    GoogleCalendarCredential,
)


# ── Helpers ─────────────────────────────────────────────────────────

def _get_pm(user):
    try:
        return user.project_manager
    except ProjectManager.DoesNotExist:
        return None


def _visible_sp_ids(user):
    if user.is_superuser or user.is_staff:
        from home.models import SalesPoint
        return list(SalesPoint.objects.filter(is_active=True).values_list("pk", flat=True))
    pm = _get_pm(user)
    if pm is None:
        return []
    return list(pm.get_visible_sales_points().values_list("pk", flat=True))


def _filter_by_sp(qs, user):
    if user.is_superuser or user.is_staff:
        return qs
    sp_ids = _visible_sp_ids(user)
    return qs.filter(Q(sales_point_id__in=sp_ids) | Q(sales_point__isnull=True))


def _default_sp(user):
    pm = _get_pm(user)
    if pm and pm.sales_point:
        return pm.sales_point
    return None


def _lead_queryset(user):
    """Return leads scoped by user role — same logic as sales dashboard."""
    qs = LeadModel.objects.select_related(
        "sales_point", "service_city", "assigned_user", "assigned_user__profile"
    )
    if user.is_superuser or user.is_staff:
        return qs
    pm = _get_pm(user)
    if pm is None:
        return qs.filter(assigned_user=user)
    if pm.role == ProjectManager.TERRITORY_MANAGER:
        return qs
    if pm.role == ProjectManager.LOCATION_MANAGER:
        managed = list(pm.extra_sales_points.values_list("pk", flat=True))
        if pm.sales_point:
            managed.append(pm.sales_point_id)
        if managed:
            return qs.filter(sales_point_id__in=managed)
        return qs.none()
    return qs.filter(assigned_user=user)


def _lead_counts(qs):
    return qs.aggregate(
        total=Count("id"),
        new_count=Count("id", filter=Q(status="new")),
        contacted_count=Count("id", filter=Q(status="contacted")),
        appointment_count=Count("id", filter=Q(status="appointment_set")),
        quoted_count=Count("id", filter=Q(status="quoted")),
        won_count=Count("id", filter=Q(status="closed_won")),
        lost_count=Count("id", filter=Q(status="closed_lost")),
    )


# ── Help (renders docs/GUIDE.md) ────────────────────────────────────

@login_required
def help_page(request):
    """Render docs/GUIDE.md as the in-panel help page.

    The markdown file is the single source of truth — edit it and the
    page reflects the change on next request.
    """
    import os
    from django.conf import settings
    from django.http import Http404
    import markdown as _md

    guide_path = os.path.join(settings.BASE_DIR, "docs", "GUIDE.md")
    try:
        with open(guide_path, "r", encoding="utf-8") as f:
            source = f.read()
    except FileNotFoundError:
        raise Http404("Guide not found.")

    md = _md.Markdown(extensions=["extra", "tables", "fenced_code", "toc"])
    body_html = md.convert(source)
    toc_html = md.toc

    return render(request, "panel/help.html", {
        "body_html": body_html,
        "toc_html": toc_html,
    })


# ── Dashboard ───────────────────────────────────────────────────────
@login_required
def dashboard(request):
    pm = _get_pm(request.user)
    customers = _filter_by_sp(Customer.objects.all(), request.user)
    projects = _filter_by_sp(Project.objects.all(), request.user)
    estimates = _filter_by_sp(Estimate.objects.all(), request.user)
    invoices = _filter_by_sp(Invoice.objects.all(), request.user)
    tasks = Task.objects.filter(is_completed=False)
    leads = _lead_queryset(request.user)
    lead_counts = _lead_counts(leads)

    # Follow-up reminders for the dashboard widget
    visible_lead_ids = leads.values_list("pk", flat=True)
    upcoming_followups = (
        LeadFollowUp.objects
        .filter(lead_id__in=visible_lead_ids, is_sent=False)
        .select_related("lead", "lead__assigned_user")
        .order_by("remind_at")[:10]
    )
    needs_attention_followups = (
        LeadFollowUp.objects
        .filter(lead_id__in=visible_lead_ids, is_sent=True, acknowledged_at__isnull=True)
        .select_related("lead", "lead__assigned_user")
        .order_by("-sent_at")[:10]
    )

    context = {
        "total_projects": projects.count(),
        "total_customers": customers.count(),
        "estimates_pending": estimates.filter(status="sent").count(),
        "open_invoices": invoices.filter(
            status__in=["sent", "partial", "overdue"]
        ).aggregate(total=Sum("total"))["total"] or 0,
        "total_tasks": tasks.count(),
        "project_manager": pm,
        "lead_counts": lead_counts,
        "recent_leads": leads.exclude(status="closed_lost").order_by("-created_at")[:10],
        "upcoming_followups": upcoming_followups,
        "needs_attention_followups": needs_attention_followups,
    }
    return render(request, "panel/dashboard.html", context)


# ── Projects ────────────────────────────────────────────────────────
@login_required
def project_list(request):
    status = request.GET.get("status", "")
    projects = _filter_by_sp(
        Project.objects.select_related("customer", "sales_point"), request.user
    )
    if status:
        projects = projects.filter(status=status)
    return render(request, "panel/projects/list.html", {
        "projects": projects,
        "current_status": status,
    })


@login_required
def project_detail(request, pk):
    project = get_object_or_404(
        _filter_by_sp(Project.objects.select_related("customer"), request.user), pk=pk
    )
    return render(request, "panel/projects/detail.html", {"project": project})


@login_required
def project_create(request):
    customers = _filter_by_sp(Customer.objects.all(), request.user)
    if request.method == "POST":
        project = Project.objects.create(
            name=request.POST["name"],
            customer_id=request.POST["customer"],
            sales_point=_default_sp(request.user),
            description=request.POST.get("description", ""),
            status=request.POST.get("status", "not_started"),
        )
        return redirect("panel:project_detail", pk=project.pk)
    return render(request, "panel/projects/form.html", {"customers": customers})


@login_required
def project_edit(request, pk):
    project = get_object_or_404(
        _filter_by_sp(Project.objects.all(), request.user), pk=pk
    )
    customers = _filter_by_sp(Customer.objects.all(), request.user)
    if request.method == "POST":
        project.name = request.POST["name"]
        project.customer_id = request.POST["customer"]
        project.description = request.POST.get("description", "")
        project.status = request.POST.get("status", project.status)
        project.save()
        return redirect("panel:project_detail", pk=project.pk)
    return render(request, "panel/projects/form.html", {
        "project": project,
        "customers": customers,
    })


@login_required
def project_delete(request, pk):
    project = get_object_or_404(
        _filter_by_sp(Project.objects.all(), request.user), pk=pk
    )
    if request.method == "POST":
        project.delete()
        return redirect("panel:project_list")
    return render(request, "panel/projects/delete.html", {"project": project})


# ── Customers ───────────────────────────────────────────────────────
@login_required
def customer_list(request):
    q = request.GET.get("q", "")
    customers = _filter_by_sp(Customer.objects.all(), request.user)
    if q:
        customers = customers.filter(
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(email__icontains=q) |
            Q(phone__icontains=q)
        )
    return render(request, "panel/customers/list.html", {
        "customers": customers,
        "search_query": q,
    })


@login_required
def customer_detail(request, pk):
    customer = get_object_or_404(
        _filter_by_sp(Customer.objects.all(), request.user), pk=pk
    )
    return render(request, "panel/customers/detail.html", {"customer": customer})


@login_required
def customer_create(request):
    if request.method == "POST":
        customer = Customer.objects.create(
            first_name=request.POST["first_name"],
            last_name=request.POST["last_name"],
            email=request.POST.get("email", ""),
            phone=request.POST.get("phone", ""),
            address=request.POST.get("address", ""),
            city=request.POST.get("city", ""),
            state=request.POST.get("state", ""),
            zip_code=request.POST.get("zip_code", ""),
            notes=request.POST.get("notes", ""),
            sales_point=_default_sp(request.user),
        )
        return redirect("panel:customer_detail", pk=customer.pk)
    return render(request, "panel/customers/form.html")


@login_required
def customer_edit(request, pk):
    customer = get_object_or_404(
        _filter_by_sp(Customer.objects.all(), request.user), pk=pk
    )
    if request.method == "POST":
        customer.first_name = request.POST["first_name"]
        customer.last_name = request.POST["last_name"]
        customer.email = request.POST.get("email", "")
        customer.phone = request.POST.get("phone", "")
        customer.address = request.POST.get("address", "")
        customer.city = request.POST.get("city", "")
        customer.state = request.POST.get("state", "")
        customer.zip_code = request.POST.get("zip_code", "")
        customer.notes = request.POST.get("notes", "")
        customer.save()
        return redirect("panel:customer_detail", pk=customer.pk)
    return render(request, "panel/customers/form.html", {"customer": customer})


@login_required
def customer_delete(request, pk):
    customer = get_object_or_404(
        _filter_by_sp(Customer.objects.all(), request.user), pk=pk
    )
    if request.method == "POST":
        customer.delete()
        return redirect("panel:customer_list")
    return render(request, "panel/customers/delete.html", {"customer": customer})


# ── Estimates ───────────────────────────────────────────────────────
@login_required
def estimate_list(request):
    estimates = _filter_by_sp(
        Estimate.objects.select_related("customer"), request.user
    )
    status = request.GET.get("status", "")
    year = request.GET.get("year", "")
    if status:
        estimates = estimates.filter(status=status)
    if year:
        estimates = estimates.filter(created_at__year=year)

    years = Estimate.objects.dates("created_at", "year", order="DESC")
    year_list = [d.year for d in years]

    return render(request, "panel/estimates/list.html", {
        "estimates": estimates,
        "current_status": status,
        "current_year": year,
        "year_list": year_list,
        "status_choices": Estimate.STATUS_CHOICES,
    })


@login_required
def estimate_detail(request, pk):
    estimate = get_object_or_404(
        _filter_by_sp(Estimate.objects.select_related("customer"), request.user), pk=pk
    )
    return render(request, "panel/estimates/detail.html", {"estimate": estimate})


@login_required
def estimate_create(request):
    customers = _filter_by_sp(Customer.objects.all(), request.user)
    if request.method == "POST":
        number = f"EST-{timezone.now().strftime('%Y%m%d-%H%M%S')}"
        estimate = Estimate.objects.create(
            estimate_number=number,
            title=request.POST["title"],
            customer_id=request.POST["customer"],
            description=request.POST.get("description", ""),
            tax_rate=request.POST.get("tax_rate", 0),
            created_by=request.user,
            sales_point=_default_sp(request.user),
        )
        estimate.ensure_main_component()
        return redirect("panel:estimate_detail", pk=estimate.pk)
    return render(request, "panel/estimates/form.html", {"customers": customers})


@login_required
def estimate_edit(request, pk):
    """Single-page estimate builder: all sections + line items inline."""
    sp = _default_sp(request.user)
    estimate = get_object_or_404(
        _filter_by_sp(Estimate.objects.select_related("customer"), request.user), pk=pk
    )
    estimate.ensure_main_component()
    components = estimate.components.prefetch_related("items").all()
    categories = _active_categories(sp)
    return render(request, "panel/estimates/edit.html", {
        "estimate": estimate,
        "components": components,
        "categories": categories,
    })


@login_required
def estimate_component_edit(request, pk, component_pk):
    """Per-component editor: add/edit parts scoped to a single non-main component."""
    sp = _default_sp(request.user)
    estimate = get_object_or_404(
        _filter_by_sp(Estimate.objects.select_related("customer"), request.user), pk=pk
    )
    component = get_object_or_404(EstimateComponent, pk=component_pk, estimate=estimate)
    categories = _active_categories(sp)
    return render(request, "panel/estimates/component_edit.html", {
        "estimate": estimate,
        "component": component,
        "categories": categories,
    })


@require_POST
@login_required
def ajax_estimate_send(request, pk):
    """Mark an estimate as sent and email the customer a summary."""
    from django.conf import settings as dj_settings
    from django.core.mail import EmailMultiAlternatives

    estimate = get_object_or_404(
        _filter_by_sp(Estimate.objects.select_related("customer", "sales_point"), request.user),
        pk=pk,
    )
    customer = estimate.customer
    if not customer or not customer.email:
        return JsonResponse({"ok": False, "error": "Customer has no email on file."}, status=400)

    items = list(estimate.items.all().order_by("order"))
    if not items:
        return JsonResponse({"ok": False, "error": "Add at least one item before sending."}, status=400)

    from_email = dj_settings.DEFAULT_FROM_EMAIL
    if estimate.sales_point and getattr(estimate.sales_point, "from_email", None):
        from_email = estimate.sales_point.from_email

    subject = f"Your Estimate from Garage Lions — {estimate.estimate_number}"

    components = list(estimate.components.prefetch_related("items").all())
    # Items not assigned to any component (legacy fallback) get an "Other" bucket.
    orphan_items = [it for it in items if it.component_id is None]

    rows_html = ""
    rows_text = ""

    def _section_html(label, section_items):
        section_html = (
            f"<tr><td colspan='5' style='padding:14px 10px 6px; font-weight:600; color:#111827; "
            f"background:#f3f4f6; border-bottom:1px solid #e5e7eb'>{label}</td></tr>"
        )
        section_subtotal = Decimal("0")
        for it in section_items:
            line_total = it.quantity * it.unit_price
            section_subtotal += line_total
            section_html += (
                f"<tr>"
                f"<td style='padding:8px 10px; border-bottom:1px solid #e5e7eb'>{it.name}</td>"
                f"<td style='padding:8px 10px; border-bottom:1px solid #e5e7eb; color:#6b7280'>{it.category_label or '—'}</td>"
                f"<td style='padding:8px 10px; border-bottom:1px solid #e5e7eb; text-align:right'>{it.quantity} {it.unit_label}</td>"
                f"<td style='padding:8px 10px; border-bottom:1px solid #e5e7eb; text-align:right'>${it.unit_price:.2f}</td>"
                f"<td style='padding:8px 10px; border-bottom:1px solid #e5e7eb; text-align:right; font-weight:600'>${line_total:.2f}</td>"
                f"</tr>"
            )
        section_html += (
            f"<tr><td colspan='4' style='padding:6px 10px; text-align:right; color:#6b7280; "
            f"border-bottom:1px solid #e5e7eb'>{label} subtotal</td>"
            f"<td style='padding:6px 10px; text-align:right; font-weight:600; "
            f"border-bottom:1px solid #e5e7eb'>${section_subtotal:.2f}</td></tr>"
        )
        return section_html, section_subtotal

    def _section_text(label, section_items):
        out = f"\n{label}\n"
        section_subtotal = Decimal("0")
        for it in section_items:
            line_total = it.quantity * it.unit_price
            section_subtotal += line_total
            out += f"  - {it.name}: {it.quantity} {it.unit_label} × ${it.unit_price:.2f} = ${line_total:.2f}\n"
        out += f"  {label} subtotal: ${section_subtotal:.2f}\n"
        return out

    for comp in components:
        comp_items = list(comp.items.all().order_by("order"))
        if not comp_items:
            continue
        section_html, _ = _section_html(comp.name, comp_items)
        rows_html += section_html
        rows_text += _section_text(comp.name, comp_items)

    if orphan_items:
        section_html, _ = _section_html("Other", orphan_items)
        rows_html += section_html
        rows_text += _section_text("Other", orphan_items)

    html_body = (
        f"<div style='font-family:system-ui,Arial,sans-serif; max-width:640px; margin:0 auto; color:#111827'>"
        f"<h2 style='margin:0 0 4px'>{estimate.title}</h2>"
        f"<p style='color:#6b7280; margin:0 0 24px'>Estimate {estimate.estimate_number}</p>"
        f"<p>Hi {customer.first_name or customer.full_name},</p>"
        f"<p>Please find your estimate from Garage Lions below. Reply to this email or call us with any questions.</p>"
        f"<table style='width:100%; border-collapse:collapse; margin-top:16px; font-size:14px'>"
        f"<thead><tr style='background:#f9fafb; text-align:left'>"
        f"<th style='padding:8px 10px; border-bottom:1px solid #e5e7eb'>Item</th>"
        f"<th style='padding:8px 10px; border-bottom:1px solid #e5e7eb'>Category</th>"
        f"<th style='padding:8px 10px; border-bottom:1px solid #e5e7eb; text-align:right'>Qty</th>"
        f"<th style='padding:8px 10px; border-bottom:1px solid #e5e7eb; text-align:right'>Unit Price</th>"
        f"<th style='padding:8px 10px; border-bottom:1px solid #e5e7eb; text-align:right'>Total</th>"
        f"</tr></thead><tbody>{rows_html}</tbody></table>"
        f"<table style='width:100%; margin-top:14px; font-size:14px'>"
        f"<tr><td style='text-align:right; color:#6b7280'>Subtotal</td><td style='text-align:right; width:120px'>${estimate.subtotal:.2f}</td></tr>"
        f"<tr><td style='text-align:right; color:#6b7280'>Tax ({estimate.tax_rate}%)</td><td style='text-align:right'>${estimate.tax:.2f}</td></tr>"
        f"<tr><td style='text-align:right; font-weight:700; font-size:16px'>Total</td><td style='text-align:right; font-weight:700; font-size:16px'>${estimate.total:.2f}</td></tr>"
        f"</table>"
        f"<p style='margin-top:24px; color:#6b7280; font-size:13px'>Thank you,<br>The Garage Lions Team<br>www.garagelions.com</p>"
        f"</div>"
    )
    text_body = (
        f"{estimate.title}\nEstimate {estimate.estimate_number}\n\n"
        f"Hi {customer.first_name or customer.full_name},\n\n"
        f"Please find your estimate from Garage Lions below. Reply or call with any questions.\n\n"
        f"Items:\n{rows_text}\n"
        f"Subtotal: ${estimate.subtotal:.2f}\n"
        f"Tax ({estimate.tax_rate}%): ${estimate.tax:.2f}\n"
        f"Total: ${estimate.total:.2f}\n\n"
        f"Thank you,\nThe Garage Lions Team\nwww.garagelions.com\n"
    )

    try:
        msg = EmailMultiAlternatives(
            subject=subject, body=text_body,
            from_email=from_email, to=[customer.email], reply_to=[from_email],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=False)
    except Exception as exc:
        return JsonResponse({"ok": False, "error": f"Email failed: {exc}"}, status=500)

    estimate.status = "sent"
    estimate.sent_at = timezone.now()
    estimate.save(update_fields=["status", "sent_at", "updated_at"])

    return JsonResponse({
        "ok": True,
        "sent_to": customer.email,
        "sent_at": estimate.sent_at.isoformat(),
        "status_label": estimate.get_status_display(),
    })


@require_POST
@login_required
def ajax_estimate_update_header(request, pk):
    """AJAX: update estimate title/description/tax_rate."""
    estimate = get_object_or_404(Estimate, pk=pk)
    field = request.POST.get("field")
    value = request.POST.get("value", "")

    if field == "title":
        estimate.title = value
        estimate.save(update_fields=["title"])
    elif field == "description":
        estimate.description = value
        estimate.save(update_fields=["description"])
    elif field == "tax_rate":
        try:
            estimate.tax_rate = Decimal(value or "0")
        except DecimalInvalid:
            estimate.tax_rate = Decimal("0")
        estimate.save(update_fields=["tax_rate"])
        estimate.recalc_totals()

    return JsonResponse({"ok": True})


@require_GET
@login_required
def ajax_estimate_search_parts(request, pk):
    """AJAX: search parts library for the add bar."""
    sp = _default_sp(request.user)
    q = (request.GET.get("q") or "").strip()
    browse = request.GET.get("browse") == "1"

    qs = _visible_parts(sp)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(sku__icontains=q))[:10]
    elif browse:
        qs = qs.order_by("category__name", "name")[:300]
    else:
        return JsonResponse({"ok": True, "results": []})

    # Get location price overrides
    price_map = {}
    unit_map = {}
    if sp:
        for spp in SalesPointPart.objects.filter(sales_point=sp).select_related("custom_unit"):
            if spp.custom_price is not None:
                price_map[spp.part_id] = spp.custom_price
            if spp.custom_unit:
                unit_map[spp.part_id] = spp.custom_unit

    results = []
    for p in qs:
        if p.sales_point is None and sp:
            price = price_map.get(p.pk, Decimal("0.00"))
            unit_obj = unit_map.get(p.pk, p.unit)
        else:
            price = p.unit_price
            unit_obj = p.unit
        results.append({
            "id": p.id,
            "name": p.name,
            "sku": p.sku or "",
            "unit_price": str(price),
            "unit": unit_obj.abbreviation if unit_obj else "",
            "category": p.category.name if p.category else "",
        })

    return JsonResponse({"ok": True, "results": results})


@require_POST
@login_required
def ajax_estimate_add_item(request, pk):
    """AJAX: add an item to the estimate (from part or custom)."""
    estimate = get_object_or_404(Estimate, pk=pk)

    part_id = request.POST.get("part_id")
    name = (request.POST.get("name") or "").strip()

    try:
        qty = Decimal(request.POST.get("quantity") or "1")
    except DecimalInvalid:
        qty = Decimal("1")
    try:
        price = Decimal(request.POST.get("unit_price") or "0")
    except DecimalInvalid:
        price = Decimal("0")

    unit_label = (request.POST.get("unit_label") or "").strip()
    category_label = (request.POST.get("category_label") or "").strip()
    cost_type = (request.POST.get("cost_type") or "").strip()

    sp = _default_sp(request.user)

    if part_id:
        part = Part.objects.filter(pk=part_id).first()
        if part:
            name = name or part.name
            # Use location price/unit for global parts
            if part.sales_point is None and sp:
                spp = SalesPointPart.objects.filter(sales_point=sp, part=part).select_related("custom_unit").first()
                if spp:
                    price = price or (spp.custom_price if spp.custom_price is not None else Decimal("0"))
                    unit_label = unit_label or (spp.custom_unit.abbreviation if spp.custom_unit else (part.unit.abbreviation if part.unit else ""))
                else:
                    unit_label = unit_label or (part.unit.abbreviation if part.unit else "")
            else:
                price = price or part.unit_price
                unit_label = unit_label or (part.unit.abbreviation if part.unit else "")
            category_label = category_label or (part.category.name if part.category else "")
            cost_type = cost_type or part.cost_type
    else:
        part = None

    if not name:
        return JsonResponse({"ok": False, "error": "Item name is required."}, status=400)
    if cost_type not in {"material", "labor", "sub"}:
        cost_type = "material"

    component = _resolve_component(estimate, request.POST.get("component_id"))

    order = estimate.items.count()
    item = EstimateItem.objects.create(
        estimate=estimate,
        component=component,
        part=part,
        name=name,
        quantity=qty,
        unit_price=price,
        unit_label=unit_label,
        category_label=category_label,
        cost_type=cost_type,
        order=order,
    )
    estimate.recalc_totals()

    return JsonResponse({
        "ok": True,
        "item": {
            "id": item.id,
            "name": item.name,
            "unit_label": item.unit_label,
            "quantity": str(item.quantity),
            "category_label": item.category_label,
            "unit_price": str(item.unit_price),
            "cost_type": item.cost_type,
            "line_total": str(item.line_total),
            "component_id": component.id if component else None,
        },
        "component_subtotal": str(component.subtotal) if component else "0.00",
        "subtotal": str(estimate.subtotal),
        "tax": str(estimate.tax),
        "total": str(estimate.total),
    })


def _resolve_component(estimate, component_id):
    """Return the EstimateComponent for the given id, falling back to the Main component."""
    if component_id:
        comp = estimate.components.filter(pk=component_id).first()
        if comp:
            return comp
    return estimate.ensure_main_component()


def _dec(value, default="0"):
    try:
        return Decimal(str(value).strip() or default)
    except (DecimalInvalid, AttributeError):
        return Decimal(default)


@require_POST
@login_required
def ajax_estimate_add_part(request, pk):
    """Multi-row add: one click creates up to 3 EstimateItems (material/labor/sub)."""
    estimate = get_object_or_404(
        _filter_by_sp(Estimate.objects.all(), request.user), pk=pk,
    )
    name = (request.POST.get("description") or request.POST.get("name") or "").strip()
    if not name:
        return JsonResponse({"ok": False, "error": "Description is required."}, status=400)

    category_label = (request.POST.get("category_label") or "").strip()
    unit_label = (request.POST.get("unit_label") or "").strip()
    quantity = _dec(request.POST.get("quantity"), "1")
    component = _resolve_component(estimate, request.POST.get("component_id"))

    rows = []
    for ct in ("material", "labor", "sub"):
        if (request.POST.get(f"{ct}_enabled") or "") not in ("1", "true", "on"):
            continue
        rows.append({
            "cost_type": ct,
            "unit_price": _dec(request.POST.get(f"{ct}_unit_price"), "0"),
            "multiplier": _dec(request.POST.get(f"{ct}_multiplier"), "1"),
            "markup_pct": _dec(request.POST.get(f"{ct}_markup_pct"), "0"),
        })
    if not rows:
        return JsonResponse({"ok": False, "error": "Enable at least one cost type."}, status=400)

    base_order = estimate.items.count()
    created = []
    for i, r in enumerate(rows):
        item = EstimateItem.objects.create(
            estimate=estimate,
            component=component,
            name=name,
            quantity=quantity,
            unit_price=r["unit_price"],
            multiplier=r["multiplier"],
            markup_pct=r["markup_pct"],
            cost_type=r["cost_type"],
            unit_label=unit_label,
            category_label=category_label,
            order=base_order + i,
        )
        created.append(item)
    estimate.recalc_totals()

    return JsonResponse({
        "ok": True,
        "items": [{
            "id": it.id,
            "name": it.name,
            "unit_label": it.unit_label,
            "quantity": str(it.quantity),
            "category_label": it.category_label,
            "unit_price": str(it.unit_price),
            "multiplier": str(it.multiplier),
            "markup_pct": str(it.markup_pct),
            "cost_type": it.cost_type,
            "line_total": str(it.line_total),
            "component_id": component.id,
        } for it in created],
        "component_subtotal": str(component.subtotal),
        "subtotal": str(estimate.subtotal),
        "tax": str(estimate.tax),
        "total": str(estimate.total),
        "cost_subtotal": str(estimate.cost_subtotal),
        "markup_amount": str(estimate.markup_amount),
    })


@require_POST
@login_required
def ajax_estimate_add_component(request, pk):
    estimate = get_object_or_404(
        _filter_by_sp(Estimate.objects.all(), request.user), pk=pk,
    )
    name = (request.POST.get("name") or "").strip() or "New Component"
    last_order = estimate.components.count()
    comp = EstimateComponent.objects.create(estimate=estimate, name=name, order=last_order)
    return JsonResponse({
        "ok": True,
        "component": {
            "id": comp.id,
            "name": comp.name,
            "subtotal": "0.00",
        },
    })


@require_POST
@login_required
def ajax_estimate_update_component(request, pk, component_pk):
    comp = get_object_or_404(EstimateComponent, pk=component_pk, estimate_id=pk)
    name = (request.POST.get("name") or "").strip()
    if name:
        comp.name = name[:120]
        comp.save(update_fields=["name"])
    return JsonResponse({"ok": True, "component": {"id": comp.id, "name": comp.name}})


@require_POST
@login_required
def ajax_estimate_delete_component(request, pk, component_pk):
    """Delete a component and cascade-delete its items. Refuses to delete the last component."""
    estimate = get_object_or_404(
        _filter_by_sp(Estimate.objects.all(), request.user), pk=pk,
    )
    comp = get_object_or_404(EstimateComponent, pk=component_pk, estimate=estimate)
    if estimate.components.count() <= 1:
        return JsonResponse(
            {"ok": False, "error": "An estimate must have at least one component."},
            status=400,
        )
    comp.delete()
    estimate.recalc_totals()
    return JsonResponse({
        "ok": True,
        "subtotal": str(estimate.subtotal),
        "tax": str(estimate.tax),
        "total": str(estimate.total),
    })


# ── Estimate templates ──────────────────────────────────────────────
@login_required
def ajax_estimate_templates_list(request, pk):
    """AJAX: list templates available to the current user."""
    sp = _default_sp(request.user)
    qs = EstimateTemplate.objects.all()
    # Show global templates + templates from user's own sales point.
    if sp:
        qs = qs.filter(Q(sales_point__isnull=True) | Q(sales_point=sp))
    elif not (request.user.is_staff or request.user.is_superuser):
        qs = qs.filter(sales_point__isnull=True)

    results = []
    for t in qs.prefetch_related("items"):
        results.append({
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "is_global": t.sales_point_id is None,
            "item_count": t.items.count(),
            "total": str(sum(i.quantity * i.unit_price for i in t.items.all())),
        })
    return JsonResponse({"ok": True, "results": results})


@require_POST
@login_required
def ajax_estimate_template_save(request, pk):
    """AJAX: save the current estimate's items as a new template."""
    estimate = get_object_or_404(Estimate, pk=pk)
    name = (request.POST.get("name") or "").strip()
    description = (request.POST.get("description") or "").strip()
    scope = (request.POST.get("scope") or "location").strip()

    if not name:
        return JsonResponse({"ok": False, "error": "Template name is required."}, status=400)
    if not estimate.items.exists():
        return JsonResponse({"ok": False, "error": "Add at least one item before saving as a template."}, status=400)

    sp = _default_sp(request.user)
    use_sp = sp
    if scope == "global" and (request.user.is_staff or request.user.is_superuser):
        use_sp = None

    template = EstimateTemplate.objects.create(
        name=name, description=description,
        sales_point=use_sp, created_by=request.user,
    )
    for item in estimate.items.all().order_by("order"):
        EstimateTemplateItem.objects.create(
            template=template, part=item.part, name=item.name,
            description=item.description, category_label=item.category_label,
            unit_label=item.unit_label, quantity=item.quantity,
            unit_price=item.unit_price, order=item.order,
        )
    return JsonResponse({"ok": True, "id": template.id, "name": template.name})


@require_POST
@login_required
def ajax_estimate_template_apply(request, pk, template_pk):
    """AJAX: append every item from the given template to this estimate."""
    estimate = get_object_or_404(Estimate, pk=pk)
    template = get_object_or_404(EstimateTemplate, pk=template_pk)
    component = _resolve_component(estimate, request.POST.get("component_id"))

    base_order = estimate.items.count()
    added = []
    for i, ti in enumerate(template.items.all().order_by("order")):
        item = EstimateItem.objects.create(
            estimate=estimate, component=component, part=ti.part, name=ti.name,
            description=ti.description, category_label=ti.category_label,
            unit_label=ti.unit_label, quantity=ti.quantity,
            unit_price=ti.unit_price, order=base_order + i,
        )
        added.append({
            "id": item.id, "name": item.name, "unit_label": item.unit_label,
            "quantity": str(item.quantity), "category_label": item.category_label,
            "unit_price": str(item.unit_price), "cost_type": item.cost_type,
            "line_total": str(item.line_total),
            "component_id": component.id if component else None,
        })
    estimate.recalc_totals()

    return JsonResponse({
        "ok": True, "items": added,
        "component_id": component.id if component else None,
        "component_subtotal": str(component.subtotal) if component else "0.00",
        "subtotal": str(estimate.subtotal),
        "tax": str(estimate.tax),
        "total": str(estimate.total),
    })


@require_POST
@login_required
def ajax_estimate_package_apply(request, pk, package_pk):
    """AJAX: add one EstimateItem to this estimate based on the given package."""
    estimate = get_object_or_404(Estimate, pk=pk)
    pkg = get_object_or_404(EstimatePackage, pk=package_pk)

    if pkg.sales_point_id is not None:
        sp = _default_sp(request.user)
        if not (request.user.is_staff or request.user.is_superuser) and (not sp or pkg.sales_point_id != sp.id):
            return JsonResponse({"ok": False, "error": "Package not available."}, status=403)

    try:
        qty = Decimal(request.POST.get("quantity") or "1")
    except DecimalInvalid:
        return JsonResponse({"ok": False, "error": "Quantity must be a number."}, status=400)

    component = _resolve_component(estimate, request.POST.get("component_id"))
    order = estimate.items.count()
    item = EstimateItem.objects.create(
        estimate=estimate, component=component,
        name=pkg.name, description=pkg.description,
        unit_label=pkg.unit.abbreviation if pkg.unit else "",
        quantity=qty, unit_price=pkg.unit_price,
        cost_type=pkg.cost_type, order=order,
    )
    estimate.recalc_totals()

    return JsonResponse({
        "ok": True,
        "item": {
            "id": item.id, "name": item.name, "unit_label": item.unit_label,
            "quantity": str(item.quantity), "category_label": item.category_label,
            "unit_price": str(item.unit_price), "cost_type": item.cost_type,
            "line_total": str(item.line_total),
            "component_id": component.id if component else None,
        },
        "component_id": component.id if component else None,
        "component_subtotal": str(component.subtotal) if component else "0.00",
        "subtotal": str(estimate.subtotal),
        "tax": str(estimate.tax),
        "total": str(estimate.total),
    })


@require_POST
@login_required
def ajax_estimate_template_delete(request, pk, template_pk):
    template = get_object_or_404(EstimateTemplate, pk=template_pk)
    if template.sales_point_id is None and not (request.user.is_staff or request.user.is_superuser):
        return JsonResponse({"ok": False, "error": "Only admins can delete global templates."}, status=403)
    template.delete()
    return JsonResponse({"ok": True})


@require_POST
@login_required
def ajax_estimate_update_item(request, pk, item_pk):
    """AJAX: update an estimate item inline."""
    item = get_object_or_404(EstimateItem, pk=item_pk, estimate_id=pk)

    name = request.POST.get("name")
    if name is not None:
        item.name = name.strip()
    qty = request.POST.get("quantity")
    if qty is not None:
        try:
            item.quantity = Decimal(qty)
        except DecimalInvalid:
            pass
    price = request.POST.get("unit_price")
    if price is not None:
        try:
            item.unit_price = Decimal(price)
        except DecimalInvalid:
            pass
    unit_label = request.POST.get("unit_label")
    if unit_label is not None:
        item.unit_label = unit_label.strip()
    cat = request.POST.get("category_label")
    if cat is not None:
        item.category_label = cat.strip()
    cost_type = request.POST.get("cost_type")
    if cost_type is not None and cost_type in {"material", "labor", "sub"}:
        item.cost_type = cost_type

    item.save()
    item.estimate.recalc_totals()
    comp = item.component

    return JsonResponse({
        "ok": True,
        "item": {
            "id": item.id,
            "name": item.name,
            "unit_label": item.unit_label,
            "quantity": str(item.quantity),
            "category_label": item.category_label,
            "unit_price": str(item.unit_price),
            "cost_type": item.cost_type,
            "line_total": str(item.line_total),
            "component_id": comp.id if comp else None,
        },
        "component_subtotal": str(comp.subtotal) if comp else "0.00",
        "subtotal": str(item.estimate.subtotal),
        "tax": str(item.estimate.tax),
        "total": str(item.estimate.total),
    })


@require_POST
@login_required
def ajax_estimate_delete_item(request, pk, item_pk):
    """AJAX: delete an estimate item."""
    item = get_object_or_404(EstimateItem, pk=item_pk, estimate_id=pk)
    estimate = item.estimate
    component_id = item.component_id
    item.delete()
    estimate.recalc_totals()

    component_subtotal = "0.00"
    if component_id:
        comp = estimate.components.filter(pk=component_id).first()
        if comp:
            component_subtotal = str(comp.subtotal)

    return JsonResponse({
        "ok": True,
        "component_id": component_id,
        "component_subtotal": component_subtotal,
        "subtotal": str(estimate.subtotal),
        "tax": str(estimate.tax),
        "total": str(estimate.total),
    })


@login_required
def ajax_estimate_list_other(request, pk):
    """AJAX: list other estimates for move target picker."""
    estimates = Estimate.objects.exclude(pk=pk).order_by("-created_at")[:20]
    return JsonResponse({
        "ok": True,
        "estimates": [
            {"id": e.id, "title": e.title, "number": e.estimate_number}
            for e in estimates
        ],
    })


@require_POST
@login_required
def ajax_estimate_move_items(request, pk):
    """AJAX: move items from this estimate to another."""
    import json
    source = get_object_or_404(Estimate, pk=pk)
    target_id = request.POST.get("target_id")
    item_ids = request.POST.getlist("item_ids[]")

    target = get_object_or_404(Estimate, pk=target_id)

    items = EstimateItem.objects.filter(pk__in=item_ids, estimate=source)
    moved = 0
    for item in items:
        item.estimate = target
        item.order = target.items.count()
        item.save()
        moved += 1

    source.recalc_totals()
    target.recalc_totals()

    return JsonResponse({
        "ok": True,
        "moved": moved,
        "subtotal": str(source.subtotal),
        "tax": str(source.tax),
        "total": str(source.total),
    })


# ── Invoices ────────────────────────────────────────────────────────
@login_required
def invoice_list(request):
    invoices = _filter_by_sp(
        Invoice.objects.select_related("customer"), request.user
    )
    return render(request, "panel/invoices/list.html", {"invoices": invoices})


@login_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(
        _filter_by_sp(Invoice.objects.select_related("customer"), request.user), pk=pk
    )
    return render(request, "panel/invoices/detail.html", {"invoice": invoice})


@login_required
def invoice_create(request):
    customers = _filter_by_sp(Customer.objects.all(), request.user)
    if request.method == "POST":
        number = f"INV-{timezone.now().strftime('%Y%m%d-%H%M%S')}"
        invoice = Invoice.objects.create(
            invoice_number=number,
            title=request.POST["title"],
            customer_id=request.POST["customer"],
            due_date=request.POST.get("due_date") or None,
            tax_rate=request.POST.get("tax_rate", 0),
            notes=request.POST.get("notes", ""),
            created_by=request.user,
            sales_point=_default_sp(request.user),
        )
        return redirect("panel:invoice_detail", pk=invoice.pk)
    return render(request, "panel/invoices/form.html", {"customers": customers})


# ── Transactions ────────────────────────────────────────────────────
@login_required
def transaction_list(request):
    transactions = Transaction.objects.select_related("customer", "invoice")
    return render(request, "panel/transactions/list.html", {
        "transactions": transactions,
    })


@login_required
def transaction_create(request):
    customers = _filter_by_sp(Customer.objects.all(), request.user)
    invoices = _filter_by_sp(
        Invoice.objects.filter(status__in=["sent", "partial", "overdue"]), request.user
    )
    if request.method == "POST":
        Transaction.objects.create(
            transaction_type=request.POST["transaction_type"],
            amount=request.POST["amount"],
            description=request.POST.get("description", ""),
            date=request.POST["date"],
            customer_id=request.POST.get("customer") or None,
            invoice_id=request.POST.get("invoice") or None,
        )
        return redirect("panel:transaction_list")
    return render(request, "panel/transactions/form.html", {
        "customers": customers,
        "invoices": invoices,
    })


# ── Parts helpers ───────────────────────────────────────────────────

def _active_categories(sales_point):
    """Categories visible to a SalesPoint: enabled globals + local ones."""
    if sales_point is None:
        return PartCategory.objects.filter(
            sales_point__isnull=True, is_active=True
        ).order_by("order", "name")

    enabled_global_ids = SalesPointPartCategory.objects.filter(
        sales_point=sales_point
    ).values_list("category_id", flat=True)

    return PartCategory.objects.filter(
        is_active=True
    ).filter(
        Q(id__in=enabled_global_ids) | Q(sales_point=sales_point)
    ).order_by("order", "name")


def _parts_table_context(sp, parts_qs):
    """Build context dict for _parts_table.html with location prices and units."""
    overrides = {}
    if sp:
        for spp in SalesPointPart.objects.filter(sales_point=sp).select_related("custom_unit"):
            overrides[spp.part_id] = spp

    parts_with_price = []
    for p in parts_qs:
        if p.sales_point is None and sp and p.pk in overrides:
            spp = overrides[p.pk]
            price = spp.custom_price if spp.custom_price is not None else Decimal("0.00")
            unit = spp.custom_unit if spp.custom_unit else p.unit
        elif p.sales_point is None and sp:
            price = Decimal("0.00")
            unit = p.unit
        else:
            price = p.unit_price
            unit = p.unit
        parts_with_price.append({
            "obj": p,
            "effective_price": price,
            "effective_unit": unit,
        })
    return {"parts_list": parts_with_price}


def _visible_parts(sales_point):
    """Parts visible to a SalesPoint: all active globals + this SP's local parts."""
    if sales_point is None:
        return Part.objects.filter(is_active=True).select_related("category", "unit").order_by("name")

    return Part.objects.filter(
        is_active=True
    ).filter(
        Q(sales_point__isnull=True) |
        Q(sales_point=sales_point)
    ).select_related("category", "unit").order_by("name")


# ── Parts page ──────────────────────────────────────────────────────
@login_required
def part_list(request):
    sp = _default_sp(request.user)
    selected_categories = _active_categories(sp)
    units = Unit.objects.all().order_by("name")

    if sp:
        enabled_ids = SalesPointPartCategory.objects.filter(
            sales_point=sp
        ).values_list("category_id", flat=True)
        suggested_global = PartCategory.objects.filter(
            sales_point__isnull=True, is_active=True
        ).exclude(id__in=enabled_ids).order_by("order", "name")
    else:
        suggested_global = PartCategory.objects.none()

    # Units: active for this location + suggested global
    active_units = _active_units(sp)
    if sp:
        enabled_unit_ids = SalesPointUnit.objects.filter(
            sales_point=sp
        ).values_list("unit_id", flat=True)
        suggested_units = Unit.objects.filter(
            sales_point__isnull=True, is_active=True
        ).exclude(id__in=enabled_unit_ids).order_by("name")
    else:
        suggested_units = Unit.objects.none()

    is_admin = request.user.is_staff or request.user.is_superuser
    return render(request, "panel/parts/list.html", {
        "selected_categories": selected_categories,
        "suggested_global": suggested_global,
        "units": active_units,
        "suggested_units": suggested_units,
        "sales_point": sp,
        "is_admin": is_admin,
    })


@require_GET
@login_required
def ajax_parts_list(request):
    sp = _default_sp(request.user)
    qs = _visible_parts(sp)

    q = (request.GET.get("q") or "").strip()
    category_id = (request.GET.get("category") or "").strip()

    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(sku__icontains=q))
    if category_id:
        qs = qs.filter(category_id=category_id)

    html = render_to_string("panel/parts/_parts_table.html", _parts_table_context(sp, qs), request=request)
    return JsonResponse({"ok": True, "html": html})


@require_POST
@login_required
def ajax_parts_create(request):
    sp = _default_sp(request.user)
    is_admin = request.user.is_staff or request.user.is_superuser
    target_sp = None if is_admin else sp

    name = (request.POST.get("name") or "").strip()
    if not name:
        return JsonResponse({"ok": False, "error": "Part name is required."}, status=400)

    sku = (request.POST.get("sku") or "").strip()
    category_id = (request.POST.get("category_id") or "").strip()
    unit_id = (request.POST.get("unit_id") or "").strip()
    notes = (request.POST.get("notes") or "").strip()
    cost_type = (request.POST.get("cost_type") or "material").strip()
    if cost_type not in {"material", "labor", "sub"}:
        cost_type = "material"

    try:
        unit_price = Decimal(request.POST.get("unit_price") or "0")
    except DecimalInvalid:
        return JsonResponse({"ok": False, "error": "Unit price must be a number."}, status=400)

    if Part.objects.filter(name__iexact=name, cost_type=cost_type, sales_point=target_sp).exists():
        return JsonResponse({"ok": False, "error": "A part with this name and cost type already exists."}, status=400)

    Part.objects.create(
        name=name,
        sales_point=target_sp,
        sku=sku,
        category_id=category_id or None,
        unit_id=unit_id or None,
        unit_price=unit_price,
        cost_type=cost_type,
        notes=notes,
    )

    qs = _visible_parts(sp)
    html = render_to_string("panel/parts/_parts_table.html", _parts_table_context(sp, qs), request=request)
    return JsonResponse({"ok": True, "html": html})


@require_POST
@login_required
def ajax_parts_create_multi(request):
    """Multi-row part creation: one click creates 1-3 Part records (one per enabled cost type)."""
    sp = _default_sp(request.user)
    is_admin = request.user.is_staff or request.user.is_superuser
    target_sp = None if is_admin else sp

    name = (request.POST.get("description") or request.POST.get("name") or "").strip()
    if not name:
        return JsonResponse({"ok": False, "error": "Description is required."}, status=400)
    sku = (request.POST.get("sku") or "").strip()
    category_id = (request.POST.get("category_id") or "").strip() or None
    unit_label = (request.POST.get("unit_label") or "").strip()
    notes = (request.POST.get("notes") or "").strip()

    # Resolve unit FK by abbreviation or name match (best-effort; otherwise None).
    unit_id = None
    if unit_label:
        u = Unit.objects.filter(
            Q(sales_point=target_sp) | Q(sales_point__isnull=True),
            Q(abbreviation__iexact=unit_label) | Q(name__iexact=unit_label),
            is_active=True,
        ).order_by("sales_point").first()
        if u:
            unit_id = u.id

    rows = []
    for ct in ("material", "labor", "sub"):
        if (request.POST.get(f"{ct}_enabled") or "") not in ("1", "true", "on"):
            continue
        try:
            unit_price = Decimal(request.POST.get(f"{ct}_unit_price") or "0")
        except DecimalInvalid:
            unit_price = Decimal("0")
        try:
            multiplier = Decimal(request.POST.get(f"{ct}_multiplier") or "1")
        except DecimalInvalid:
            multiplier = Decimal("1")
        rows.append({
            "cost_type": ct,
            "unit_price": (unit_price * multiplier).quantize(Decimal("0.01")),
        })
    if not rows:
        return JsonResponse({"ok": False, "error": "Enable at least one cost type."}, status=400)

    for r in rows:
        if Part.objects.filter(name__iexact=name, cost_type=r["cost_type"], sales_point=target_sp).exists():
            return JsonResponse(
                {"ok": False, "error": f"A {r['cost_type']} part named “{name}” already exists."},
                status=400,
            )

    for r in rows:
        Part.objects.create(
            name=name,
            sales_point=target_sp,
            sku=sku,
            category_id=category_id,
            unit_id=unit_id,
            unit_price=r["unit_price"],
            cost_type=r["cost_type"],
            notes=notes,
        )

    qs = _visible_parts(sp)
    html = render_to_string("panel/parts/_parts_table.html", _parts_table_context(sp, qs), request=request)
    return JsonResponse({"ok": True, "html": html, "created": len(rows)})


def _active_units(sales_point):
    """Units visible to a SalesPoint: enabled globals + local ones."""
    if sales_point is None:
        return Unit.objects.filter(sales_point__isnull=True, is_active=True).order_by("name")

    enabled_global_ids = SalesPointUnit.objects.filter(
        sales_point=sales_point
    ).values_list("unit_id", flat=True)

    return Unit.objects.filter(
        is_active=True
    ).filter(
        Q(id__in=enabled_global_ids) | Q(sales_point=sales_point)
    ).order_by("name")


@login_required
def ajax_units(request):
    sp = _default_sp(request.user)
    qs = _active_units(sp)
    return JsonResponse({
        "ok": True,
        "results": [{"id": u.id, "name": u.name, "abbr": u.abbreviation} for u in qs],
    })


@require_POST
@login_required
def ajax_category_add(request):
    """Add a custom category. If name matches a global, enable it instead.

    Admin/superuser additions always create a global category (sales_point=NULL).
    """
    sp = _default_sp(request.user)
    is_admin = request.user.is_staff or request.user.is_superuser
    name = (request.POST.get("name") or "").strip()
    if not name:
        return JsonResponse({"ok": False, "error": "Category name is required."}, status=400)

    if is_admin:
        PartCategory.objects.get_or_create(
            name__iexact=name, sales_point__isnull=True,
            defaults={"name": name, "is_active": True},
        )
        return _category_response(sp)

    global_cat = PartCategory.objects.filter(
        name__iexact=name, sales_point__isnull=True
    ).first()

    if global_cat and sp:
        SalesPointPartCategory.objects.get_or_create(
            sales_point=sp, category=global_cat
        )
    elif sp:
        PartCategory.objects.get_or_create(
            name__iexact=name, sales_point=sp,
            defaults={"name": name, "is_active": True, "sales_point": sp},
        )
    else:
        PartCategory.objects.get_or_create(
            name__iexact=name, sales_point__isnull=True,
            defaults={"name": name, "is_active": True},
        )

    return _category_response(sp)


@require_POST
@login_required
def ajax_category_add_global(request):
    """Enable a suggested global category for this location."""
    sp = _default_sp(request.user)
    category_id = request.POST.get("category_id")
    if sp and category_id:
        try:
            cat = PartCategory.objects.get(pk=category_id, sales_point__isnull=True)
            SalesPointPartCategory.objects.get_or_create(
                sales_point=sp, category=cat
            )
        except PartCategory.DoesNotExist:
            pass
    return _category_response(sp)


@require_POST
@login_required
def ajax_category_remove(request):
    """Remove a category from this location's selection."""
    sp = _default_sp(request.user)
    category_id = request.POST.get("category_id")

    try:
        cat = PartCategory.objects.get(pk=category_id)
    except PartCategory.DoesNotExist:
        return _category_response(sp)

    if cat.is_global and sp:
        if Part.objects.filter(sales_point=sp, category=cat).exists():
            return JsonResponse(
                {"ok": False, "error": "Can't remove — parts in this category exist."},
                status=400,
            )
        SalesPointPartCategory.objects.filter(
            sales_point=sp, category=cat
        ).delete()
    elif not cat.is_global and cat.sales_point == sp:
        if Part.objects.filter(category=cat).exists():
            return JsonResponse(
                {"ok": False, "error": "Can't remove — parts in this category exist."},
                status=400,
            )
        cat.is_active = False
        cat.save(update_fields=["is_active"])

    return _category_response(sp)


def _category_response(sp):
    cats = _active_categories(sp)
    selected = []
    for c in cats:
        selected.append({
            "id": c.id,
            "name": c.name,
            "is_global": c.is_global,
        })

    if sp:
        enabled_ids = SalesPointPartCategory.objects.filter(
            sales_point=sp
        ).values_list("category_id", flat=True)
        suggested = list(
            PartCategory.objects.filter(
                sales_point__isnull=True, is_active=True
            ).exclude(id__in=enabled_ids).order_by("order", "name").values("id", "name")
        )
    else:
        suggested = []

    return JsonResponse({
        "ok": True,
        "selected": selected,
        "suggested": suggested,
        "active_categories": selected,
    })


@require_POST
@login_required
def ajax_unit_add(request):
    """Add a custom unit. If name matches a global, enable it instead.

    Admin/superuser additions always create a global unit (sales_point=NULL).
    """
    sp = _default_sp(request.user)
    is_admin = request.user.is_staff or request.user.is_superuser
    name = (request.POST.get("name") or "").strip()
    abbr = (request.POST.get("abbreviation") or "").strip()
    if not name:
        return JsonResponse({"ok": False, "error": "Unit name is required."}, status=400)
    if not abbr:
        return JsonResponse({"ok": False, "error": "Abbreviation is required."}, status=400)

    if is_admin:
        if Unit.objects.filter(name__iexact=name, sales_point__isnull=True).exists():
            return JsonResponse({"ok": False, "error": "A unit with this name already exists."}, status=400)
        Unit.objects.create(name=name, abbreviation=abbr)
        return _unit_response(request.user, sp)

    global_unit = Unit.objects.filter(name__iexact=name, sales_point__isnull=True).first()

    if global_unit and sp:
        SalesPointUnit.objects.get_or_create(sales_point=sp, unit=global_unit)
    elif sp:
        Unit.objects.get_or_create(
            name__iexact=name, sales_point=sp,
            defaults={"name": name, "abbreviation": abbr, "is_active": True, "sales_point": sp},
        )
    else:
        if Unit.objects.filter(name__iexact=name, sales_point__isnull=True).exists():
            return JsonResponse({"ok": False, "error": "A unit with this name already exists."}, status=400)
        Unit.objects.create(name=name, abbreviation=abbr)

    return _unit_response(request.user, sp)


@require_POST
@login_required
def ajax_unit_add_global(request):
    """Enable a suggested global unit for this location."""
    sp = _default_sp(request.user)
    unit_id = request.POST.get("unit_id")
    if sp and unit_id:
        try:
            unit = Unit.objects.get(pk=unit_id, sales_point__isnull=True)
            SalesPointUnit.objects.get_or_create(sales_point=sp, unit=unit)
        except Unit.DoesNotExist:
            pass
    return _unit_response(request.user, sp)


@require_POST
@login_required
def ajax_unit_remove(request):
    """Remove a unit from this location's selection.

    Mirrors ajax_category_remove: removing a global unit only unlinks it from
    this location (so it remains available in the Suggested list); removing a
    local unit deactivates that local row. Global units are never deactivated
    here — that would hide them globally for every location.
    """
    sp = _default_sp(request.user)
    unit_id = request.POST.get("unit_id")

    try:
        unit = Unit.objects.get(pk=unit_id)
    except Unit.DoesNotExist:
        return _unit_response(request.user, sp)

    if unit.is_global and sp:
        SalesPointUnit.objects.filter(sales_point=sp, unit=unit).delete()
    elif not unit.is_global and unit.sales_point == sp:
        unit.is_active = False
        unit.save(update_fields=["is_active"])

    return _unit_response(request.user, sp)


def _unit_response(user=None, sp=None):
    selected = _active_units(sp)
    selected_list = [{"id": u.id, "name": u.name, "abbreviation": u.abbreviation, "is_global": u.is_global} for u in selected]

    if sp:
        enabled_ids = SalesPointUnit.objects.filter(
            sales_point=sp
        ).values_list("unit_id", flat=True)
        suggested = list(
            Unit.objects.filter(
                sales_point__isnull=True, is_active=True
            ).exclude(id__in=enabled_ids).order_by("name").values("id", "name", "abbreviation")
        )
    else:
        suggested = []

    is_admin = user and (user.is_staff or user.is_superuser) if user else False
    return JsonResponse({"ok": True, "units": selected_list, "suggested": suggested, "is_admin": is_admin})


@login_required
def part_edit(request, pk):
    sp = _default_sp(request.user)
    part = get_object_or_404(Part, pk=pk)

    # Only admin can edit global parts; local users can only edit their own
    if part.sales_point is None and not (request.user.is_staff or request.user.is_superuser):
        return redirect("panel:part_list")
    if part.sales_point and sp and part.sales_point != sp:
        return redirect("panel:part_list")

    categories = _active_categories(sp)
    units = Unit.objects.all()
    if request.method == "POST":
        part.name = request.POST["name"]
        part.sku = request.POST.get("sku", "")
        part.category_id = request.POST.get("category") or None
        part.unit_id = request.POST.get("unit") or None
        part.unit_price = request.POST.get("unit_price", 0)
        part.notes = request.POST.get("notes", "")
        part.save()
        return redirect("panel:part_list")
    return render(request, "panel/parts/form.html", {
        "part": part,
        "categories": categories,
        "units": units,
    })


@login_required
def ajax_parts_search_json(request):
    """JSON parts search used by the template editor dropdown."""
    sp = _default_sp(request.user)
    q = (request.GET.get("q") or "").strip()
    qs = _visible_parts(sp)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(sku__icontains=q))[:10]
    else:
        qs = qs.order_by("name")[:50]

    price_map, unit_map = {}, {}
    if sp:
        for spp in SalesPointPart.objects.filter(sales_point=sp).select_related("custom_unit"):
            if spp.custom_price is not None:
                price_map[spp.part_id] = spp.custom_price
            if spp.custom_unit:
                unit_map[spp.part_id] = spp.custom_unit

    results = []
    for p in qs:
        if p.sales_point is None and sp:
            price = price_map.get(p.pk, Decimal("0.00"))
            unit_obj = unit_map.get(p.pk, p.unit)
        else:
            price = p.unit_price
            unit_obj = p.unit
        results.append({
            "id": p.id, "name": p.name, "sku": p.sku or "",
            "unit_price": str(price),
            "unit": unit_obj.abbreviation if unit_obj else "",
            "category": p.category.name if p.category else "",
        })
    return JsonResponse({"ok": True, "parts": results})


# ── Estimate templates (managed on Parts page) ──────────────────────
def _user_visible_templates(user):
    sp = _default_sp(user)
    qs = EstimateTemplate.objects.all()
    if sp:
        qs = qs.filter(Q(sales_point__isnull=True) | Q(sales_point=sp))
    elif not (user.is_staff or user.is_superuser):
        qs = qs.filter(sales_point__isnull=True)
    return qs


@login_required
def ajax_templates_list(request):
    """AJAX: list templates for the Parts → Templates tab."""
    qs = _user_visible_templates(request.user).prefetch_related("items")
    is_admin = request.user.is_staff or request.user.is_superuser
    results = []
    for t in qs:
        results.append({
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "is_global": t.sales_point_id is None,
            "item_count": t.items.count(),
            "total": str(sum(i.quantity * i.unit_price for i in t.items.all())),
            "can_delete": bool(is_admin or t.sales_point_id is not None),
            "edit_url": reverse("panel:template_edit", args=[t.id]),
        })
    return JsonResponse({"ok": True, "results": results})


@require_POST
@login_required
def ajax_template_create(request):
    """AJAX: create an empty template, return URL to edit page."""
    name = (request.POST.get("name") or "").strip()
    description = (request.POST.get("description") or "").strip()
    scope = (request.POST.get("scope") or "location").strip()

    if not name:
        return JsonResponse({"ok": False, "error": "Template name is required."}, status=400)

    sp = _default_sp(request.user)
    use_sp = sp
    if scope == "global" and (request.user.is_staff or request.user.is_superuser):
        use_sp = None

    template = EstimateTemplate.objects.create(
        name=name, description=description,
        sales_point=use_sp, created_by=request.user,
    )
    return JsonResponse({
        "ok": True,
        "id": template.id,
        "edit_url": reverse("panel:template_edit", args=[template.id]),
    })


@require_POST
@login_required
def ajax_template_delete(request, pk):
    template = get_object_or_404(EstimateTemplate, pk=pk)
    if template.sales_point_id is None and not (request.user.is_staff or request.user.is_superuser):
        return JsonResponse({"ok": False, "error": "Only admins can delete global templates."}, status=403)
    template.delete()
    return JsonResponse({"ok": True})


def _can_edit_template(user, template):
    if template.sales_point_id is None:
        return user.is_staff or user.is_superuser
    sp = _default_sp(user)
    return user.is_staff or user.is_superuser or (sp and template.sales_point_id == sp.id)


@login_required
def template_edit(request, pk):
    template = get_object_or_404(EstimateTemplate, pk=pk)
    if not _can_edit_template(request.user, template):
        return redirect("panel:part_list")

    if request.method == "POST":
        template.name = (request.POST.get("name") or template.name).strip() or template.name
        template.description = (request.POST.get("description") or "").strip()
        template.save(update_fields=["name", "description", "updated_at"])
        return redirect("panel:part_list")

    items = template.items.all().order_by("order")
    total = sum(i.quantity * i.unit_price for i in items)
    return render(request, "panel/parts/template_edit.html", {
        "template": template,
        "items": items,
        "total": total,
    })


@require_POST
@login_required
def ajax_template_add_item(request, pk):
    template = get_object_or_404(EstimateTemplate, pk=pk)
    if not _can_edit_template(request.user, template):
        return JsonResponse({"ok": False, "error": "Permission denied."}, status=403)

    part_id = request.POST.get("part_id")
    name = (request.POST.get("name") or "").strip()
    try:
        qty = Decimal(request.POST.get("quantity") or "1")
    except DecimalInvalid:
        qty = Decimal("1")
    try:
        price = Decimal(request.POST.get("unit_price") or "0")
    except DecimalInvalid:
        price = Decimal("0")
    unit_label = (request.POST.get("unit_label") or "").strip()
    category_label = (request.POST.get("category_label") or "").strip()

    sp = _default_sp(request.user)
    part = None
    if part_id:
        part = Part.objects.filter(pk=part_id).first()
        if part:
            name = name or part.name
            if part.sales_point is None and sp:
                spp = SalesPointPart.objects.filter(sales_point=sp, part=part).select_related("custom_unit").first()
                if spp:
                    price = price or (spp.custom_price if spp.custom_price is not None else Decimal("0"))
                    unit_label = unit_label or (spp.custom_unit.abbreviation if spp.custom_unit else (part.unit.abbreviation if part.unit else ""))
                else:
                    unit_label = unit_label or (part.unit.abbreviation if part.unit else "")
            else:
                price = price or part.unit_price
                unit_label = unit_label or (part.unit.abbreviation if part.unit else "")
            category_label = category_label or (part.category.name if part.category else "")

    if not name:
        return JsonResponse({"ok": False, "error": "Item name is required."}, status=400)

    order = template.items.count()
    item = EstimateTemplateItem.objects.create(
        template=template, part=part, name=name,
        quantity=qty, unit_price=price,
        unit_label=unit_label, category_label=category_label,
        order=order,
    )
    return JsonResponse({
        "ok": True,
        "item": {
            "id": item.id, "name": item.name,
            "quantity": str(item.quantity), "unit_price": str(item.unit_price),
            "unit_label": item.unit_label, "category_label": item.category_label,
            "line_total": str(item.quantity * item.unit_price),
        },
        "total": str(sum(i.quantity * i.unit_price for i in template.items.all())),
    })


@require_POST
@login_required
def ajax_template_update_item(request, pk, item_pk):
    template = get_object_or_404(EstimateTemplate, pk=pk)
    if not _can_edit_template(request.user, template):
        return JsonResponse({"ok": False, "error": "Permission denied."}, status=403)
    item = get_object_or_404(EstimateTemplateItem, pk=item_pk, template=template)

    qty = request.POST.get("quantity")
    if qty is not None:
        try: item.quantity = Decimal(qty)
        except DecimalInvalid: pass
    price = request.POST.get("unit_price")
    if price is not None:
        try: item.unit_price = Decimal(price)
        except DecimalInvalid: pass
    item.save()
    return JsonResponse({
        "ok": True,
        "item": {
            "id": item.id, "name": item.name,
            "quantity": str(item.quantity), "unit_price": str(item.unit_price),
            "line_total": str(item.quantity * item.unit_price),
        },
        "total": str(sum(i.quantity * i.unit_price for i in template.items.all())),
    })


@require_POST
@login_required
def ajax_template_delete_item(request, pk, item_pk):
    template = get_object_or_404(EstimateTemplate, pk=pk)
    if not _can_edit_template(request.user, template):
        return JsonResponse({"ok": False, "error": "Permission denied."}, status=403)
    EstimateTemplateItem.objects.filter(pk=item_pk, template=template).delete()
    return JsonResponse({
        "ok": True,
        "total": str(sum(i.quantity * i.unit_price for i in template.items.all())),
    })


# ── Estimate packages (managed on Parts page) ───────────────────────
def _user_visible_packages(user):
    sp = _default_sp(user)
    qs = EstimatePackage.objects.filter(is_active=True)
    if sp:
        qs = qs.filter(Q(sales_point__isnull=True) | Q(sales_point=sp))
    elif not (user.is_staff or user.is_superuser):
        qs = qs.filter(sales_point__isnull=True)
    return qs


def _can_edit_package(user, pkg):
    if pkg.sales_point_id is None:
        return user.is_staff or user.is_superuser
    sp = _default_sp(user)
    return user.is_staff or user.is_superuser or (sp and pkg.sales_point_id == sp.id)


@login_required
def ajax_packages_list(request):
    """AJAX: list packages for the Parts → Packages tab."""
    qs = _user_visible_packages(request.user).select_related("unit")
    is_admin = request.user.is_staff or request.user.is_superuser
    results = []
    for p in qs:
        results.append({
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "unit_id": p.unit_id,
            "unit_label": p.unit.abbreviation if p.unit else "",
            "unit_name": p.unit.name if p.unit else "",
            "unit_price": str(p.unit_price),
            "cost_type": p.cost_type,
            "cost_type_label": p.get_cost_type_display(),
            "is_global": p.sales_point_id is None,
            "can_edit": _can_edit_package(request.user, p),
            "can_delete": bool(is_admin or p.sales_point_id is not None),
        })
    return JsonResponse({"ok": True, "results": results})


def _parse_package_post(request):
    name = (request.POST.get("name") or "").strip()
    description = (request.POST.get("description") or "").strip()
    unit_id = (request.POST.get("unit_id") or "").strip() or None
    unit_price_raw = (request.POST.get("unit_price") or "0").strip()
    cost_type = (request.POST.get("cost_type") or "material").strip()
    try:
        unit_price = Decimal(unit_price_raw or "0")
    except DecimalInvalid:
        return None, "Unit price must be a number."
    if not name:
        return None, "Package name is required."
    if cost_type not in {"material", "labor", "sub"}:
        return None, "Cost type must be Material, Labor, or Subcontractor."
    if unit_id:
        if not Unit.objects.filter(pk=unit_id).exists():
            return None, "Unknown unit."
    return {
        "name": name,
        "description": description,
        "unit_id": unit_id,
        "unit_price": unit_price,
        "cost_type": cost_type,
    }, None


@require_POST
@login_required
def ajax_package_create(request):
    data, err = _parse_package_post(request)
    if err:
        return JsonResponse({"ok": False, "error": err}, status=400)

    sp = _default_sp(request.user)
    scope = (request.POST.get("scope") or "location").strip()
    use_sp = sp
    if scope == "global" and (request.user.is_staff or request.user.is_superuser):
        use_sp = None

    pkg = EstimatePackage.objects.create(
        sales_point=use_sp, created_by=request.user, **data,
    )
    return JsonResponse({"ok": True, "id": pkg.id})


@require_POST
@login_required
def ajax_package_update(request, pk):
    pkg = get_object_or_404(EstimatePackage, pk=pk)
    if not _can_edit_package(request.user, pkg):
        return JsonResponse({"ok": False, "error": "Permission denied."}, status=403)

    data, err = _parse_package_post(request)
    if err:
        return JsonResponse({"ok": False, "error": err}, status=400)

    for field, value in data.items():
        setattr(pkg, field, value)
    pkg.save(update_fields=list(data.keys()) + ["updated_at"])
    return JsonResponse({"ok": True, "id": pkg.id})


@require_POST
@login_required
def ajax_package_delete(request, pk):
    pkg = get_object_or_404(EstimatePackage, pk=pk)
    is_admin = request.user.is_staff or request.user.is_superuser
    if pkg.sales_point_id is None and not is_admin:
        return JsonResponse({"ok": False, "error": "Only admins can delete global packages."}, status=403)
    if not _can_edit_package(request.user, pkg):
        return JsonResponse({"ok": False, "error": "Permission denied."}, status=403)
    pkg.delete()
    return JsonResponse({"ok": True})


@require_POST
@login_required
def ajax_parts_delete(request):
    """AJAX: remove a part. Global = un-enable, Local = deactivate."""
    sp = _default_sp(request.user)
    part_id = request.POST.get("part_id")
    part = Part.objects.filter(pk=part_id).first()
    if part:
        if part.sales_point is None and sp:
            # Un-enable global part for this location
            SalesPointPart.objects.filter(sales_point=sp, part=part).delete()
        elif part.sales_point is None and not sp:
            # Admin deactivating a global part
            if request.user.is_staff or request.user.is_superuser:
                part.is_active = False
                part.save(update_fields=["is_active"])
        elif part.sales_point == sp or request.user.is_staff or request.user.is_superuser:
            # Deactivate local part
            part.is_active = False
            part.save(update_fields=["is_active"])

    qs = _visible_parts(sp)
    html = render_to_string("panel/parts/_parts_table.html", _parts_table_context(sp, qs), request=request)
    return JsonResponse({"ok": True, "html": html})


@require_GET
@login_required
def ajax_global_parts_list(request):
    """AJAX: return global parts NOT yet enabled, grouped by category."""
    sp = _default_sp(request.user)
    if not sp:
        return JsonResponse({"ok": True, "categories": []})

    enabled_ids = SalesPointPart.objects.filter(
        sales_point=sp
    ).values_list("part_id", flat=True)

    qs = Part.objects.filter(
        sales_point__isnull=True, is_active=True
    ).exclude(id__in=enabled_ids).select_related("category", "unit").order_by("category__name", "name")

    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(sku__icontains=q))

    # Group by category
    from collections import OrderedDict
    grouped = OrderedDict()
    for p in qs:
        cat_name = p.category.name if p.category else "Uncategorized"
        if cat_name not in grouped:
            grouped[cat_name] = []
        grouped[cat_name].append({
            "id": p.id,
            "name": p.name,
            "sku": p.sku or "",
            "unit": p.unit.abbreviation if p.unit else "",
        })

    categories = [{"name": k, "parts": v} for k, v in grouped.items()]
    return JsonResponse({"ok": True, "categories": categories})


@require_POST
@login_required
def ajax_parts_update_price(request):
    """AJAX: update price, unit, name, SKU on a part."""
    sp = _default_sp(request.user)
    part_id = request.POST.get("part_id")
    price_raw = request.POST.get("price")
    unit_id_raw = request.POST.get("unit_id")
    name = request.POST.get("name")
    sku = request.POST.get("sku")

    part = Part.objects.filter(pk=part_id).first()
    if not part:
        return JsonResponse({"ok": False, "error": "Part not found."}, status=404)

    # Parse unit_id safely
    unit_id = None
    if unit_id_raw is not None and unit_id_raw.strip():
        try:
            unit_id = int(unit_id_raw)
        except (ValueError, TypeError):
            unit_id = None

    if part.sales_point is None and sp:
        # Global part — save overrides on SalesPointPart
        spp = SalesPointPart.objects.filter(sales_point=sp, part=part).first()
        if spp:
            if price_raw is not None:
                try:
                    spp.custom_price = Decimal(price_raw or "0")
                except DecimalInvalid:
                    pass
            if unit_id_raw is not None:
                spp.custom_unit_id = unit_id
            spp.save()
    else:
        # Local part — save directly
        if price_raw is not None:
            try:
                part.unit_price = Decimal(price_raw or "0")
            except DecimalInvalid:
                pass
        if unit_id_raw is not None:
            part.unit_id = unit_id
        if name is not None:
            part.name = name.strip()
        if sku is not None:
            part.sku = sku.strip()
        part.save()

    return JsonResponse({"ok": True})


@require_GET
@login_required
def ajax_part_detail(request):
    """AJAX: get part info for the edit modal."""
    sp = _default_sp(request.user)
    part_id = request.GET.get("part_id")
    part = Part.objects.filter(pk=part_id).select_related("category", "unit").first()
    if not part:
        return JsonResponse({"ok": False, "error": "Part not found."}, status=404)

    # Get effective price and unit for this location
    price = part.unit_price if part.sales_point else Decimal("0.00")
    unit_id = part.unit_id or ""
    if part.sales_point is None and sp:
        spp = SalesPointPart.objects.filter(sales_point=sp, part=part).first()
        if spp:
            price = spp.custom_price if spp.custom_price is not None else Decimal("0.00")
            if spp.custom_unit_id:
                unit_id = spp.custom_unit_id

    return JsonResponse({
        "ok": True,
        "part": {
            "id": part.id,
            "name": part.name,
            "sku": part.sku or "",
            "is_global": part.sales_point is None,
            "price": str(price),
            "unit_id": unit_id or "",
        },
    })


@require_POST
@login_required
def ajax_parts_add_global(request):
    """AJAX: enable a global part for this location."""
    sp = _default_sp(request.user)
    part_id = request.POST.get("part_id")
    if sp and part_id:
        try:
            part = Part.objects.get(pk=part_id, sales_point__isnull=True, is_active=True)
            SalesPointPart.objects.get_or_create(sales_point=sp, part=part)
        except Part.DoesNotExist:
            pass

    qs = _visible_parts(sp)
    html = render_to_string("panel/parts/_parts_table.html", _parts_table_context(sp, qs), request=request)
    return JsonResponse({"ok": True, "html": html})


# ── Tasks ───────────────────────────────────────────────────────────
@login_required
def task_list(request):
    task_lists = TaskList.objects.prefetch_related("tasks").all()
    return render(request, "panel/tasks/list.html", {"task_lists": task_lists})


@login_required
def task_list_create(request):
    if request.method == "POST":
        TaskList.objects.create(
            name=request.POST["name"],
            created_by=request.user,
        )
        return redirect("panel:task_list")
    return render(request, "panel/tasks/list_form.html")


@login_required
def task_create(request, list_pk):
    tl = get_object_or_404(TaskList, pk=list_pk)
    if request.method == "POST":
        Task.objects.create(
            task_list=tl,
            title=request.POST["title"],
            notes=request.POST.get("notes", ""),
            due_date=request.POST.get("due_date") or None,
        )
        return redirect("panel:task_list")
    return render(request, "panel/tasks/task_form.html", {"task_list": tl})


@login_required
def task_toggle(request, pk):
    task = get_object_or_404(Task, pk=pk)
    task.is_completed = not task.is_completed
    task.save(update_fields=["is_completed"])
    return redirect("panel:task_list")


# ── Leads ───────────────────────────────────────────────────────────
@never_cache
@login_required
def lead_list(request):
    qs = _lead_queryset(request.user)
    pm = _get_pm(request.user)

    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    sales_point_id = request.GET.get("sales_point", "").strip()
    sort = request.GET.get("sort", "").strip()

    if q:
        qs = qs.filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q) |
            Q(email__icontains=q) | Q(phone__icontains=q) | Q(zip_code__icontains=q)
        )
    if status:
        qs = qs.filter(status=status)
    else:
        qs = qs.exclude(status__in=[
            "closed_lost", "disqualified", "may_come_back", "in_operation",
        ])

    can_filter_location = (
        request.user.is_staff or request.user.is_superuser
        or (pm and pm.role in (ProjectManager.LOCATION_MANAGER, ProjectManager.TERRITORY_MANAGER))
    )
    if sales_point_id and can_filter_location:
        qs = qs.filter(sales_point_id=sales_point_id)

    from django.db.models import DateTimeField
    qs = qs.annotate(
        pending_followup_at=Subquery(
            LeadFollowUp.objects.filter(
                lead=OuterRef("pk"), is_sent=False
            ).order_by("remind_at").values("remind_at")[:1],
            output_field=DateTimeField(),
        ),
        pending_todos_count=Subquery(
            LeadTodo.objects.filter(lead=OuterRef("pk"), is_completed=False)
            .order_by()
            .values("lead")
            .annotate(c=Count("pk"))
            .values("c")[:1],
            output_field=IntegerField(),
        ),
    )

    if sort in ("status_asc", "status_desc"):
        qs = qs.annotate(
            _status_label=Subquery(
                LeadStatus.objects.filter(code=OuterRef("status")).values("label")[:1],
                output_field=CharField(),
            )
        )
        order_field = "_status_label" if sort == "status_asc" else "-_status_label"
        qs = qs.order_by(order_field, "-created_at")
    else:
        qs = qs.annotate(
            _status_priority=Case(
                When(status="new", then=Value(0)),
                When(status="in_operation", then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            )
        ).order_by("_status_priority", "-created_at")
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    sales_points = []
    if can_filter_location:
        sales_points = SalesPoint.objects.filter(is_active=True).order_by("name")

    quick_filters = [
        {"code": s.code, "label": s.label, "bg": s.bg_hex, "fg": s.fg_hex}
        for s in LeadStatus.objects.filter(is_quick_filter=True).exclude(code="in_operation")
    ]

    bottom_codes = ["closed_lost", "disqualified", "may_come_back"]
    bottom_filter_map = {s.code: s for s in LeadStatus.objects.filter(code__in=bottom_codes)}
    bottom_filters = [
        {"code": code, "label": bottom_filter_map[code].label,
         "bg": bottom_filter_map[code].bg_hex, "fg": bottom_filter_map[code].fg_hex}
        for code in bottom_codes if code in bottom_filter_map
    ]

    view_mode = "grid" if request.GET.get("view", "").strip() == "grid" else "table"

    # In Operation badge counts (visible-to-user leads only).
    in_op_qs = _lead_queryset(request.user).filter(status="in_operation")
    in_op_count = in_op_qs.count()
    in_op_tasks_count = LeadTodo.objects.filter(
        lead__in=in_op_qs, is_completed=False
    ).count()

    return render(request, "panel/leads/list.html", {
        "page_obj": page_obj,
        "q": q,
        "status": status,
        "sales_point_id": sales_point_id,
        "sales_points": sales_points,
        "status_choices": LeadStatus.as_choices(),
        "quick_filters": quick_filters,
        "bottom_filters": bottom_filters,
        "can_filter_location": can_filter_location,
        "can_manage_statuses": request.user.is_superuser,
        "sort": sort,
        "view_mode": view_mode,
        "in_op_count": in_op_count,
        "in_op_tasks_count": in_op_tasks_count,
    })


@login_required
def lead_detail(request, pk):
    lead = get_object_or_404(_lead_queryset(request.user), pk=pk)
    pm = _get_pm(request.user)

    if request.method == "POST":
        form = LeadUpdateForm(request.POST, instance=lead)
        if form.is_valid():
            old_status = lead.status
            old_notes = lead.internal_notes
            updated = form.save()

            if updated.status != old_status:
                LeadActivity.objects.create(
                    lead=updated, user=request.user,
                    action=LeadActivity.ACTION_STATUS,
                    detail=f"Status changed to '{updated.status_label}'.",
                )
            if updated.internal_notes != old_notes:
                LeadActivity.objects.create(
                    lead=updated, user=request.user,
                    action=LeadActivity.ACTION_NOTES,
                    detail="Internal notes updated.",
                )
            return redirect("panel:lead_detail", pk=pk)
    else:
        form = LeadUpdateForm(instance=lead)

    # Mark any fired-but-unacknowledged reminders for this lead as acknowledged
    # — viewing the lead is what counts as acting on the reminder.
    lead.follow_ups.filter(is_sent=True, acknowledged_at__isnull=True).update(
        acknowledged_at=timezone.now()
    )

    pending_followup = lead.follow_ups.filter(is_sent=False).order_by("remind_at").first()

    activities = lead.activities.select_related("user", "user__profile").order_by("-created_at")[:20]
    todos = lead.todos.all()
    estimates = lead.panel_estimates.all().order_by("-created_at")

    return render(request, "panel/leads/detail.html", {
        "lead": lead,
        "form": form,
        "project_manager": pm,
        "activities": activities,
        "todos": todos,
        "pending_followup": pending_followup,
        "estimates": estimates,
    })


@login_required
@require_POST
def lead_todo_create(request, lead_pk):
    lead = get_object_or_404(_lead_queryset(request.user), pk=lead_pk)
    title = (request.POST.get("title") or "").strip()
    if title:
        LeadTodo.objects.create(lead=lead, title=title, created_by=request.user)
    return redirect("panel:lead_detail", pk=lead.pk)


@login_required
@require_POST
def lead_todo_toggle(request, lead_pk, pk):
    lead = get_object_or_404(_lead_queryset(request.user), pk=lead_pk)
    todo = get_object_or_404(LeadTodo, pk=pk, lead=lead)
    todo.is_completed = not todo.is_completed
    todo.completed_at = timezone.now() if todo.is_completed else None
    todo.save(update_fields=["is_completed", "completed_at"])
    return redirect("panel:lead_detail", pk=lead.pk)


@login_required
@require_POST
def lead_todo_delete(request, lead_pk, pk):
    lead = get_object_or_404(_lead_queryset(request.user), pk=lead_pk)
    LeadTodo.objects.filter(pk=pk, lead=lead).delete()
    return redirect("panel:lead_detail", pk=lead.pk)


# ── Lead Follow-Up Reminders ─────────────────────────────────────────

@require_GET
@login_required
def ajax_lead_followup_get(request, lead_pk):
    """Return the current pending (unsent) follow-up reminder for a lead."""
    lead = get_object_or_404(_lead_queryset(request.user), pk=lead_pk)
    fu = lead.follow_ups.filter(is_sent=False).order_by("remind_at").first()
    if not fu:
        return JsonResponse({"ok": True, "followup": None})
    local_dt = timezone.localtime(fu.remind_at)
    return JsonResponse({
        "ok": True,
        "followup": {
            "id": fu.pk,
            "remind_at": local_dt.strftime("%Y-%m-%dT%H:%M"),
            "remind_at_display": local_dt.strftime("%b %d, %Y · %I:%M %p"),
            "note": fu.note or "",
        },
    })


@require_POST
@login_required
def ajax_lead_followup_set(request, lead_pk):
    """Create or replace the pending follow-up reminder for a lead.

    Expects POST with `remind_at` (datetime-local string, e.g. 2026-05-01T14:30)
    and optional `note`. Replaces any existing unsent reminder.
    """
    from datetime import datetime
    lead = get_object_or_404(_lead_queryset(request.user), pk=lead_pk)
    raw = (request.POST.get("remind_at") or "").strip()
    note = (request.POST.get("note") or "").strip()[:255]

    if not raw:
        return JsonResponse({"ok": False, "error": "Date and time are required."}, status=400)

    try:
        naive = datetime.strptime(raw, "%Y-%m-%dT%H:%M")
    except ValueError:
        try:
            naive = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return JsonResponse({"ok": False, "error": "Invalid date/time format."}, status=400)

    aware = timezone.make_aware(naive, timezone.get_current_timezone())
    if aware <= timezone.now():
        return JsonResponse({"ok": False, "error": "Reminder must be in the future."}, status=400)

    lead.follow_ups.filter(is_sent=False).delete()
    fu = LeadFollowUp.objects.create(
        lead=lead,
        remind_at=aware,
        note=note,
        created_by=request.user,
    )
    LeadActivity.objects.create(
        lead=lead, user=request.user,
        action=LeadActivity.ACTION_NOTES,
        detail=f"Follow-up reminder scheduled for {timezone.localtime(aware).strftime('%b %d, %Y %I:%M %p')}.",
    )

    local_dt = timezone.localtime(fu.remind_at)
    return JsonResponse({
        "ok": True,
        "followup": {
            "id": fu.pk,
            "remind_at": local_dt.strftime("%Y-%m-%dT%H:%M"),
            "remind_at_display": local_dt.strftime("%b %d, %Y · %I:%M %p"),
            "note": fu.note or "",
        },
    })


@require_POST
@login_required
def ajax_lead_followup_clear(request, lead_pk):
    """Clear the pending follow-up reminder for a lead."""
    lead = get_object_or_404(_lead_queryset(request.user), pk=lead_pk)
    deleted, _ = lead.follow_ups.filter(is_sent=False).delete()
    if deleted:
        LeadActivity.objects.create(
            lead=lead, user=request.user,
            action=LeadActivity.ACTION_NOTES,
            detail="Follow-up reminder cleared.",
        )
    return JsonResponse({"ok": True})


# ── Closed Lost archive ──────────────────────────────────────────────

@login_required
def closed_lost_list(request):
    """Archive page for leads with status='closed_lost'.

    Kept separate from the main leads list so the active pipeline stays
    uncluttered. Same scoping rules as the main list — users only see
    leads they're allowed to see.
    """
    qs = _lead_queryset(request.user).filter(status="closed_lost")
    pm = _get_pm(request.user)

    q = request.GET.get("q", "").strip()
    sales_point_id = request.GET.get("sales_point", "").strip()

    if q:
        qs = qs.filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q) |
            Q(email__icontains=q) | Q(phone__icontains=q) | Q(zip_code__icontains=q)
        )

    can_filter_location = (
        request.user.is_staff or request.user.is_superuser
        or (pm and pm.role in (ProjectManager.LOCATION_MANAGER, ProjectManager.TERRITORY_MANAGER))
    )
    if sales_point_id and can_filter_location:
        qs = qs.filter(sales_point_id=sales_point_id)

    # Order by most recently lost — uses the latest status-change activity
    # if available, falling back to the lead's created_at.
    qs = qs.order_by("-created_at")

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    sales_points = []
    if can_filter_location:
        sales_points = SalesPoint.objects.filter(is_active=True).order_by("name")

    return render(request, "panel/leads/closed_lost.html", {
        "page_obj": page_obj,
        "q": q,
        "sales_point_id": sales_point_id,
        "sales_points": sales_points,
        "can_filter_location": can_filter_location,
        "total_lost": qs.count(),
    })


@login_required
def in_operation_list(request):
    """Dedicated page for leads with status='in_operation'.

    Kept off the main pipeline so active conversations stay in focus.
    Same scoping rules as the main list — users only see leads they're
    allowed to see.
    """
    qs = _lead_queryset(request.user).filter(status="in_operation")
    pm = _get_pm(request.user)

    q = request.GET.get("q", "").strip()
    sales_point_id = request.GET.get("sales_point", "").strip()

    if q:
        qs = qs.filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q) |
            Q(email__icontains=q) | Q(phone__icontains=q) | Q(zip_code__icontains=q)
        )

    can_filter_location = (
        request.user.is_staff or request.user.is_superuser
        or (pm and pm.role in (ProjectManager.LOCATION_MANAGER, ProjectManager.TERRITORY_MANAGER))
    )
    if sales_point_id and can_filter_location:
        qs = qs.filter(sales_point_id=sales_point_id)

    qs = qs.annotate(
        pending_todos_count=Subquery(
            LeadTodo.objects.filter(lead=OuterRef("pk"), is_completed=False)
            .order_by()
            .values("lead")
            .annotate(c=Count("pk"))
            .values("c")[:1],
            output_field=IntegerField(),
        ),
    ).order_by("-created_at")

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    sales_points = []
    if can_filter_location:
        sales_points = SalesPoint.objects.filter(is_active=True).order_by("name")

    return render(request, "panel/leads/in_operation.html", {
        "page_obj": page_obj,
        "q": q,
        "sales_point_id": sales_point_id,
        "sales_points": sales_points,
        "can_filter_location": can_filter_location,
        "total_in_op": qs.count(),
    })


# ── Lead Status Settings (admin-only) ────────────────────────────────

def _can_manage_lead_statuses(user):
    return user.is_authenticated and user.is_superuser


def _slugify_code(label):
    import re
    code = re.sub(r"[^a-z0-9]+", "_", (label or "").strip().lower()).strip("_")
    return code[:30]


@login_required
def lead_status_settings(request):
    if not _can_manage_lead_statuses(request.user):
        return redirect("panel:lead_list")

    valid_colors = set(LeadStatus.COLOR_PRESETS.keys())
    error = None

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "create":
            label = (request.POST.get("label") or "").strip()
            code = (request.POST.get("code") or "").strip().lower() or _slugify_code(label)
            color = (request.POST.get("color") or "gray").strip().lower()
            if color not in valid_colors:
                color = "gray"

            if not label:
                error = "Label is required."
            elif not code:
                error = "Could not derive a code from that label — please provide one."
            elif LeadStatus.objects.filter(code=code).exists():
                error = f"A status with code '{code}' already exists."
            else:
                max_order = LeadStatus.objects.order_by("-order").values_list("order", flat=True).first() or 0
                LeadStatus.objects.create(
                    code=code, label=label, order=max_order + 10,
                    color=color, is_protected=False,
                )
                return redirect("panel:lead_status_settings")

        elif action == "update_color":
            pk = request.POST.get("pk")
            color = (request.POST.get("color") or "gray").strip().lower()
            if color not in valid_colors:
                color = "gray"
            LeadStatus.objects.filter(pk=pk).update(color=color)
            return redirect("panel:lead_status_settings")

        elif action == "toggle_quick_filter":
            pk = request.POST.get("pk")
            status = LeadStatus.objects.filter(pk=pk).first()
            if status is not None:
                status.is_quick_filter = not status.is_quick_filter
                status.save(update_fields=["is_quick_filter"])
            return redirect("panel:lead_status_settings")

    statuses = LeadStatus.objects.all()
    return render(request, "panel/leads/status_settings.html", {
        "statuses": statuses,
        "color_presets": [
            {"key": k, "bg": bg, "fg": fg}
            for k, (bg, fg) in LeadStatus.COLOR_PRESETS.items()
        ],
        "error": error,
    })


@login_required
@require_POST
def lead_status_delete(request, pk):
    if not _can_manage_lead_statuses(request.user):
        return redirect("panel:lead_list")
    status = get_object_or_404(LeadStatus, pk=pk)
    if not status.is_protected:
        status.delete()
    return redirect("panel:lead_status_settings")


# ── Mobile (PWA) views — separate templates, same data ───────────────
@login_required
def m_lead_list(request):
    qs = _lead_queryset(request.user)

    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()

    if q:
        qs = qs.filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q) |
            Q(email__icontains=q) | Q(phone__icontains=q) | Q(zip_code__icontains=q)
        )
    if status:
        qs = qs.filter(status=status)

    qs = qs.annotate(
        _status_priority=Case(
            When(status="new", then=Value(0)),
            When(status="in_operation", then=Value(1)),
            default=Value(2),
            output_field=IntegerField(),
        )
    ).order_by("_status_priority", "-created_at")

    paginator = Paginator(qs, 30)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "mobile/leads/list.html", {
        "page_obj": page_obj,
        "q": q,
        "status": status,
        "status_choices": LeadStatus.as_choices(),
    })


@login_required
def m_lead_detail(request, pk):
    lead = get_object_or_404(_lead_queryset(request.user), pk=pk)

    lead.follow_ups.filter(is_sent=True, acknowledged_at__isnull=True).update(
        acknowledged_at=timezone.now()
    )

    if request.method == "POST":
        form = LeadUpdateForm(request.POST, instance=lead)
        if form.is_valid():
            old_status = lead.status
            old_notes = lead.internal_notes
            updated = form.save()

            if updated.status != old_status:
                LeadActivity.objects.create(
                    lead=updated, user=request.user,
                    action=LeadActivity.ACTION_STATUS,
                    detail=f"Status changed to '{updated.status_label}'.",
                )
            if updated.internal_notes != old_notes:
                LeadActivity.objects.create(
                    lead=updated, user=request.user,
                    action=LeadActivity.ACTION_NOTES,
                    detail="Internal notes updated.",
                )
            return redirect("panel:m_lead_detail", pk=pk)
    else:
        form = LeadUpdateForm(instance=lead)

    todos = lead.todos.all()

    return render(request, "mobile/leads/detail.html", {
        "lead": lead,
        "form": form,
        "todos": todos,
    })


@login_required
@require_POST
def m_lead_todo_create(request, lead_pk):
    lead = get_object_or_404(_lead_queryset(request.user), pk=lead_pk)
    title = (request.POST.get("title") or "").strip()
    if title:
        LeadTodo.objects.create(lead=lead, title=title, created_by=request.user)
    return redirect("panel:m_lead_detail", pk=lead.pk)


@login_required
@require_POST
def m_lead_todo_toggle(request, lead_pk, pk):
    lead = get_object_or_404(_lead_queryset(request.user), pk=lead_pk)
    todo = get_object_or_404(LeadTodo, pk=pk, lead=lead)
    todo.is_completed = not todo.is_completed
    todo.completed_at = timezone.now() if todo.is_completed else None
    todo.save(update_fields=["is_completed", "completed_at"])
    return redirect("panel:m_lead_detail", pk=lead.pk)


@login_required
@require_POST
def m_lead_todo_delete(request, lead_pk, pk):
    lead = get_object_or_404(_lead_queryset(request.user), pk=lead_pk)
    LeadTodo.objects.filter(pk=pk, lead=lead).delete()
    return redirect("panel:m_lead_detail", pk=lead.pk)


@login_required
def lead_create(request):
    pm = _get_pm(request.user)
    gcal_connected = hasattr(request.user, "gcal_credential")

    if request.method == "POST":
        form = ManualLeadForm(request.POST, user=request.user, gcal_connected=gcal_connected)
        if form.is_valid():
            lead = form.save(commit=False)
            if not lead.sales_point and pm and pm.sales_point:
                lead.sales_point = pm.sales_point
            if not lead.assigned_user:
                lead.assigned_user = request.user
            if not lead.source_page:
                lead.source_page = f"Manual entry by {request.user.get_full_name()}"
            lead.save()
            form.save_m2m()
            # Came from Google Calendar sync → return to the leads list so the
            # event no longer shows on the sync page.
            if (lead.source_page or "").startswith("google_calendar:"):
                return redirect("panel:lead_list")
            return redirect("panel:lead_detail", pk=lead.pk)
    else:
        initial = {"status": "new", "assigned_user": request.user}
        if pm and pm.sales_point:
            initial["sales_point"] = pm.sales_point
        # Prefill from querystring (used by Google Calendar sync)
        for field in (
            "first_name", "last_name", "email", "phone", "address",
            "zip_code", "message", "source_page", "status", "appointment_at",
        ):
            val = request.GET.get(field)
            if val:
                initial[field] = val
        form = ManualLeadForm(user=request.user, gcal_connected=gcal_connected, initial=initial)

    return render(request, "panel/leads/form.html", {
        "form": form,
        "gcal_connected": gcal_connected,
    })


@login_required
def lead_edit(request, pk):
    lead = get_object_or_404(_lead_queryset(request.user), pk=pk)
    gcal_connected = hasattr(request.user, "gcal_credential")

    if request.method == "POST":
        form = ManualLeadForm(request.POST, instance=lead, user=request.user, gcal_connected=gcal_connected)
        if form.is_valid():
            form.save()
            # If the save mutated fields that scope visibility (assigned_user,
            # sales_point) the user may no longer be able to see this lead via
            # _lead_queryset — fall back to the list instead of 404'ing.
            if _lead_queryset(request.user).filter(pk=lead.pk).exists():
                return redirect("panel:lead_detail", pk=lead.pk)
            return redirect("panel:lead_list")
    else:
        form = ManualLeadForm(instance=lead, user=request.user, gcal_connected=gcal_connected)

    return render(request, "panel/leads/form.html", {
        "form": form,
        "lead": lead,
        "is_edit": True,
        "gcal_connected": gcal_connected,
    })


# ── Lead to Customer + Estimate ─────────────────────────────────────
@login_required
def lead_to_estimate(request, lead_pk):
    lead = get_object_or_404(LeadModel, pk=lead_pk)

    customer, created = Customer.objects.get_or_create(
        email=lead.email,
        defaults={
            "first_name": lead.first_name,
            "last_name": lead.last_name,
            "phone": lead.phone,
            "address": lead.address,
            "zip_code": lead.zip_code,
            "sales_point": lead.sales_point,
        },
    )

    if not created:
        changed = False
        if not customer.phone and lead.phone:
            customer.phone = lead.phone
            changed = True
        if not customer.address and lead.address:
            customer.address = lead.address
            changed = True
        if not customer.zip_code and lead.zip_code:
            customer.zip_code = lead.zip_code
            changed = True
        if changed:
            customer.save()

    services = ""
    if lead.consultation_types:
        labels = dict(LeadModel.CONSULTATION_CHOICES)
        services = ", ".join(labels.get(s, s) for s in lead.consultation_types)
    title = services or f"Estimate for {customer.full_name}"

    number = f"EST-{timezone.now().strftime('%Y%m%d-%H%M%S')}"
    estimate = Estimate.objects.create(
        estimate_number=number,
        title=title,
        customer=customer,
        lead=lead,
        sales_point=lead.sales_point,
        description=lead.message or "",
        created_by=request.user,
    )
    estimate.ensure_main_component()

    if lead.status in ("new", "contacted", "appointment_set", "waiting_for_estimate"):
        lead.status = "quoted"
        lead.save(update_fields=["status"])

    return redirect("panel:estimate_detail", pk=estimate.pk)


# ── Google Calendar sync ────────────────────────────────────────────
import re as _re
from urllib.parse import urlencode as _urlencode
from django.contrib import messages as _messages

from . import google_calendar as _gcal


_PHONE_RE = _re.compile(r"(\+?\d[\d\s().-]{7,}\d)")
_ZIP_RE = _re.compile(r"\b(\d{5})(?:-\d{4})?\b")


def _extract_zip(text):
    if not text:
        return ""
    m = _ZIP_RE.search(text)
    return m.group(1) if m else ""


def _split_event_title(summary):
    """Take an event summary like "John Smith — Roof estimate" or
    "Lead: Jane Doe" and return (first_name, last_name)."""
    if not summary:
        return "", ""
    s = summary.strip()
    for sep in (" — ", " - ", ":", "|"):
        if sep in s:
            left, _ = s.split(sep, 1)
            s = left.strip()
            break
    # Strip a leading "Lead" / "Consult" / "Appointment" prefix
    s = _re.sub(r"^(lead|consult(ation)?|appointment|meeting)\s*[:\-]?\s*",
                "", s, flags=_re.IGNORECASE).strip()
    parts = s.split(None, 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return parts[0] if parts else "", ""


def _extract_phone(text):
    if not text:
        return ""
    m = _PHONE_RE.search(text)
    return m.group(1).strip() if m else ""


def _event_guest(event):
    """Return (display_name, email) for the first non-self attendee.
    Either field may be empty if the calendar event didn't include it."""
    for a in event.get("attendees") or []:
        if a.get("self"):
            continue
        email = a.get("email") or ""
        name = a.get("displayName") or ""
        if email or name:
            return name, email
    return "", ""


def _split_full_name(full):
    """Split a "First Last" string into (first, last)."""
    parts = (full or "").strip().split(None, 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return (parts[0] if parts else ""), ""


@login_required
def gcal_connect(request):
    """Kick off Google OAuth — redirect the user to Google's consent page."""
    if not _gcal.is_configured():
        _messages.error(
            request,
            "Google Calendar is not configured. Set GOOGLE_OAUTH_CLIENT_ID "
            "and GOOGLE_OAUTH_CLIENT_SECRET in your environment.",
        )
        return redirect("panel:gcal_sync")

    flow = _gcal.build_flow()
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    request.session["gcal_oauth_state"] = state
    return redirect(auth_url)


@login_required
def gcal_callback(request):
    """Handle Google's redirect after the user grants consent."""
    if request.GET.get("error"):
        _messages.error(request, f"Google Calendar: {request.GET['error']}")
        return redirect("panel:gcal_sync")

    state = request.session.pop("gcal_oauth_state", None)
    flow = _gcal.build_flow(state=state)
    try:
        flow.fetch_token(
            authorization_response=request.build_absolute_uri(),
        )
    except Exception as e:
        _messages.error(request, f"Google Calendar: could not complete sign-in ({e}).")
        return redirect("panel:gcal_sync")

    creds = flow.credentials
    email = _gcal.fetch_userinfo_email(creds)
    _gcal.save_credentials(request.user, creds, google_email=email)
    _messages.success(request, f"Google Calendar connected ({email}).")
    return redirect("panel:gcal_sync")


@login_required
def gcal_disconnect(request):
    GoogleCalendarCredential.objects.filter(user=request.user).delete()
    _messages.success(request, "Google Calendar disconnected.")
    return redirect("panel:gcal_sync")


@login_required
def gcal_sync(request):
    """List upcoming Google Calendar events and let the user create a
    Lead from each one."""
    connected = GoogleCalendarCredential.objects.filter(user=request.user).exists()
    events_ctx = []
    error = ""
    calendar_name = ""

    if connected:
        try:
            raw_events, calendar_name = _gcal.fetch_upcoming_events(request.user, days_ahead=30)
        except Exception as e:
            raw_events = []
            error = str(e)

        # Which events are already converted into leads?
        existing_sources = set(
            LeadModel.objects
            .filter(source_page__startswith="google_calendar:")
            .values_list("source_page", flat=True)
        )

        for ev in raw_events:
            event_id = ev.get("id", "")
            source_tag = _gcal.event_source_tag(event_id)
            if source_tag in existing_sources:
                continue  # already a lead — don't show it on the sync page
            summary = ev.get("summary", "(untitled event)")
            description = ev.get("description", "") or ""
            location = ev.get("location", "") or ""
            start_dt = ev.get("start", {}).get("dateTime") or ""
            start = start_dt or ev.get("start", {}).get("date") or ""
            guest_name, attendee_email = _event_guest(ev)
            if guest_name:
                first, last = _split_full_name(guest_name)
            else:
                first, last = _split_event_title(summary)
            phone = _extract_phone(description) or _extract_phone(location)

            prefill = {
                "first_name": first,
                "last_name": last,
                "email": attendee_email,
                "phone": phone,
                "address": location,
                "zip_code": _extract_zip(location) or _extract_zip(description),
                "message": (description[:1000] if description else summary),
                "source_page": source_tag,
                "status": "appointment_set",
                "appointment_at": start_dt[:16] if start_dt else "",
            }
            create_url = (
                reverse("panel:lead_create")
                + "?" + _urlencode({k: v for k, v in prefill.items() if v})
            )

            events_ctx.append({
                "id": event_id,
                "summary": summary,
                "description": description,
                "location": location,
                "start": start,
                "html_link": ev.get("htmlLink", ""),
                "attendee_email": attendee_email,
                "first_name": first,
                "last_name": last,
                "phone": phone,
                "create_url": create_url,
            })

    google_email = ""
    if connected:
        google_email = request.user.gcal_credential.google_email

    return render(request, "panel/leads/calendar_sync.html", {
        "connected": connected,
        "configured": _gcal.is_configured(),
        "google_email": google_email,
        "calendar_name": calendar_name,
        "events": events_ctx,
        "error": error,
    })


@login_required
def ajax_gcal_events_json(request):
    """Upcoming Google Calendar events for the current user, used by the
    appointment picker on the manual lead-create form."""
    if not hasattr(request.user, "gcal_credential"):
        return JsonResponse({"ok": True, "connected": False, "events": []})
    try:
        raw_events, calendar_name = _gcal.fetch_upcoming_events(request.user)
    except Exception as exc:
        return JsonResponse({
            "ok": False, "connected": True, "error": str(exc), "events": [],
        })
    events = []
    for ev in raw_events:
        start_iso = ev.get("start", {}).get("dateTime") or ""
        if not start_iso:
            continue  # skip all-day events; datetime-local needs HH:MM
        events.append({
            "id": ev.get("id", ""),
            "summary": ev.get("summary", "(untitled)"),
            "start_iso": start_iso,
            "location": ev.get("location", "") or "",
        })
    return JsonResponse({
        "ok": True,
        "connected": True,
        "calendar_name": calendar_name,
        "events": events,
    })
