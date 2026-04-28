from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Sum, Q, Case, When, IntegerField, Value, Subquery, OuterRef, CharField
from django.utils import timezone
from decimal import Decimal, InvalidOperation as DecimalInvalid
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET, require_POST

from django.core.paginator import Paginator
from django.db.models import Count

from account.models import ProjectManager
from home.models import LeadModel, LeadActivity, LeadTodo, LeadFollowUp, SalesPoint, LeadStatus
from home.forms import LeadUpdateForm, ManualLeadForm
from .models import (
    Customer, Project, Part, PartCategory, SalesPointPartCategory,
    Unit, SalesPointUnit, SalesPointPart,
    Estimate, EstimateItem, Invoice, InvoiceItem,
    Transaction, TaskList, Task,
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
        return redirect("panel:estimate_detail", pk=estimate.pk)
    return render(request, "panel/estimates/form.html", {"customers": customers})


@login_required
def estimate_edit(request, pk):
    """Interactive estimate builder page."""
    sp = _default_sp(request.user)
    estimate = get_object_or_404(
        _filter_by_sp(Estimate.objects.select_related("customer"), request.user), pk=pk
    )
    items = estimate.items.all()
    categories = _active_categories(sp)
    return render(request, "panel/estimates/edit.html", {
        "estimate": estimate,
        "items": items,
        "categories": categories,
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
    if not q:
        return JsonResponse({"ok": True, "results": []})

    qs = _visible_parts(sp).filter(
        Q(name__icontains=q) | Q(sku__icontains=q)
    )[:10]

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
    else:
        part = None

    if not name:
        return JsonResponse({"ok": False, "error": "Item name is required."}, status=400)

    order = estimate.items.count()
    item = EstimateItem.objects.create(
        estimate=estimate,
        part=part,
        name=name,
        quantity=qty,
        unit_price=price,
        unit_label=unit_label,
        category_label=category_label,
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
            "line_total": str(item.line_total),
        },
        "subtotal": str(estimate.subtotal),
        "tax": str(estimate.tax),
        "total": str(estimate.total),
    })


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

    item.save()
    item.estimate.recalc_totals()

    return JsonResponse({
        "ok": True,
        "item": {
            "id": item.id,
            "name": item.name,
            "unit_label": item.unit_label,
            "quantity": str(item.quantity),
            "category_label": item.category_label,
            "unit_price": str(item.unit_price),
            "line_total": str(item.line_total),
        },
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
    item.delete()
    estimate.recalc_totals()

    return JsonResponse({
        "ok": True,
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
        ).order_by("name")

    enabled_global_ids = SalesPointPartCategory.objects.filter(
        sales_point=sales_point
    ).values_list("category_id", flat=True)

    return PartCategory.objects.filter(
        is_active=True
    ).filter(
        Q(id__in=enabled_global_ids) | Q(sales_point=sales_point)
    ).order_by("name")


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
    """Parts visible to a SalesPoint: enabled globals + local."""
    if sales_point is None:
        return Part.objects.filter(is_active=True).select_related("category", "unit").order_by("name")

    enabled_global_ids = SalesPointPart.objects.filter(
        sales_point=sales_point
    ).values_list("part_id", flat=True)

    return Part.objects.filter(
        is_active=True
    ).filter(
        Q(id__in=enabled_global_ids) |
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
        ).exclude(id__in=enabled_ids).order_by("name")
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

    name = (request.POST.get("name") or "").strip()
    if not name:
        return JsonResponse({"ok": False, "error": "Part name is required."}, status=400)

    sku = (request.POST.get("sku") or "").strip()
    category_id = (request.POST.get("category_id") or "").strip()
    unit_id = (request.POST.get("unit_id") or "").strip()
    notes = (request.POST.get("notes") or "").strip()

    try:
        unit_price = Decimal(request.POST.get("unit_price") or "0")
    except DecimalInvalid:
        return JsonResponse({"ok": False, "error": "Unit price must be a number."}, status=400)

    if Part.objects.filter(name__iexact=name, sales_point=sp).exists():
        return JsonResponse({"ok": False, "error": "A part with this name already exists."}, status=400)

    Part.objects.create(
        name=name,
        sales_point=sp,
        sku=sku,
        category_id=category_id or None,
        unit_id=unit_id or None,
        unit_price=unit_price,
        notes=notes,
    )

    qs = _visible_parts(sp)
    html = render_to_string("panel/parts/_parts_table.html", _parts_table_context(sp, qs), request=request)
    return JsonResponse({"ok": True, "html": html})


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
    """Add a custom category. If name matches a global, enable it instead."""
    sp = _default_sp(request.user)
    name = (request.POST.get("name") or "").strip()
    if not name:
        return JsonResponse({"ok": False, "error": "Category name is required."}, status=400)

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
        SalesPointPartCategory.objects.filter(
            sales_point=sp, category=cat
        ).delete()
    elif not cat.is_global and cat.sales_point == sp:
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
            ).exclude(id__in=enabled_ids).order_by("name").values("id", "name")
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
    """Add a custom unit. If name matches a global, enable it instead."""
    sp = _default_sp(request.user)
    name = (request.POST.get("name") or "").strip()
    abbr = (request.POST.get("abbreviation") or "").strip()
    if not name:
        return JsonResponse({"ok": False, "error": "Unit name is required."}, status=400)
    if not abbr:
        return JsonResponse({"ok": False, "error": "Abbreviation is required."}, status=400)

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
    """Remove a unit from this location's selection."""
    sp = _default_sp(request.user)
    unit_id = request.POST.get("unit_id")

    try:
        unit = Unit.objects.get(pk=unit_id)
    except Unit.DoesNotExist:
        return _unit_response(request.user, sp)

    if unit.is_global and sp:
        # Un-enable the global unit for this location
        SalesPointUnit.objects.filter(sales_point=sp, unit=unit).delete()
    elif unit.is_global and not sp:
        # Admin deleting a global unit
        if request.user.is_staff or request.user.is_superuser:
            unit.is_active = False
            unit.save(update_fields=["is_active"])
    elif not unit.is_global and (unit.sales_point == sp or request.user.is_staff or request.user.is_superuser):
        # Delete local unit
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
        # Closed Lost lives on its own archive page — keep the active list focused.
        qs = qs.exclude(status="closed_lost")

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
        )
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

    quick_codes = ["new", "in_operation", "follow_up"]
    quick_filter_map = {s.code: s for s in LeadStatus.objects.filter(code__in=quick_codes)}
    quick_filters = [
        {"code": code, "label": quick_filter_map[code].label,
         "bg": quick_filter_map[code].bg_hex, "fg": quick_filter_map[code].fg_hex}
        for code in quick_codes if code in quick_filter_map
    ]

    return render(request, "panel/leads/list.html", {
        "page_obj": page_obj,
        "q": q,
        "status": status,
        "sales_point_id": sales_point_id,
        "sales_points": sales_points,
        "status_choices": LeadStatus.as_choices(),
        "quick_filters": quick_filters,
        "can_filter_location": can_filter_location,
        "can_manage_statuses": request.user.is_staff or request.user.is_superuser,
        "sort": sort,
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

    return render(request, "panel/leads/detail.html", {
        "lead": lead,
        "form": form,
        "project_manager": pm,
        "activities": activities,
        "todos": todos,
        "pending_followup": pending_followup,
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


# ── Lead Status Settings (admin-only) ────────────────────────────────

def _can_manage_lead_statuses(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


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

    if request.method == "POST":
        form = ManualLeadForm(request.POST, user=request.user)
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
            return redirect("panel:lead_detail", pk=lead.pk)
    else:
        initial = {"status": "new", "assigned_user": request.user}
        if pm and pm.sales_point:
            initial["sales_point"] = pm.sales_point
        form = ManualLeadForm(user=request.user, initial=initial)

    return render(request, "panel/leads/form.html", {"form": form})


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
        sales_point=lead.sales_point,
        description=lead.message or "",
        created_by=request.user,
    )

    if lead.status in ("new", "contacted", "appointment_set", "waiting_for_estimate"):
        lead.status = "quoted"
        lead.save(update_fields=["status"])

    return redirect("panel:estimate_detail", pk=estimate.pk)
