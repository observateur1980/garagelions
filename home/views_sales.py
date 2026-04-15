# home/views_sales.py
#
# Three separate dashboards, one lead list, one lead detail.
# Access is gated by the ProjectManager.role field.
# Superusers and is_staff users always see everything.

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from account.models import ProjectManager
from .forms import LeadUpdateForm
from .models import LeadActivity, LeadModel, SalesPoint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_project_manager(user):
    """Return the ProjectManager record or None."""
    try:
        return user.project_manager
    except ProjectManager.DoesNotExist:
        return None


def _lead_queryset(user):
    """
    Return the base LeadModel queryset scoped to what this user may see.

    - Superuser / is_staff         → all leads
    - Territory Manager            → all leads (across all locations)
    - Location Manager             → all leads for their SalesPoint
    - Project Manager              → only leads assigned to them
    - No ProjectManager record     → only leads assigned to them (fallback)
    """
    qs = LeadModel.objects.select_related(
        'sales_point', 'service_city', 'assigned_user', 'assigned_user__profile'
    )

    if user.is_superuser or user.is_staff:
        return qs

    sp = _get_project_manager(user)
    if sp is None:
        return qs.filter(assigned_user=user)

    if sp.role == ProjectManager.TERRITORY_MANAGER:
        return qs

    if sp.role == ProjectManager.LOCATION_MANAGER:
        managed = list(sp.extra_sales_points.values_list('pk', flat=True))
        if sp.sales_point:
            managed.append(sp.sales_point_id)
        if managed:
            return qs.filter(sales_point_id__in=managed)
        return qs.none()

    # Default: salesperson sees only their own leads
    return qs.filter(assigned_user=user)


def _counts(qs):
    agg = qs.aggregate(
        total=Count('id'),
        new_count=Count('id', filter=Q(status='new')),
        contacted_count=Count('id', filter=Q(status='contacted')),
        appointment_count=Count('id', filter=Q(status='appointment_set')),
        quoted_count=Count('id', filter=Q(status='quoted')),
        won_count=Count('id', filter=Q(status='closed_won')),
        lost_count=Count('id', filter=Q(status='closed_lost')),
    )
    return agg


# ---------------------------------------------------------------------------
# Role guard decorators
# ---------------------------------------------------------------------------

def project_manager_required(view_func):
    """User must be logged in AND have a ProjectManager record (or be staff)."""
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.is_staff or request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        sp = _get_project_manager(request.user)
        if sp is None:
            return redirect('account:login')
        return view_func(request, *args, **kwargs)
    return wrapper


def manager_required(view_func):
    """User must be a Location Manager, Territory Manager, or staff."""
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.is_staff or request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        sp = _get_project_manager(request.user)
        if sp and sp.role in (ProjectManager.LOCATION_MANAGER, ProjectManager.TERRITORY_MANAGER):
            return view_func(request, *args, **kwargs)
        return redirect('sales_dashboard')
    return wrapper


def territory_required(view_func):
    """User must be a Territory Manager or staff/superuser."""
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.is_staff or request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        sp = _get_project_manager(request.user)
        if sp and sp.role == ProjectManager.TERRITORY_MANAGER:
            return view_func(request, *args, **kwargs)
        return redirect('sales_dashboard')
    return wrapper


# ---------------------------------------------------------------------------
# Dashboard: Project Manager (default)
# ---------------------------------------------------------------------------

@login_required
def sales_dashboard(request):
    qs = _lead_queryset(request.user)
    sp = _get_project_manager(request.user)

    return render(request, 'sales/dashboard.html', {
        'counts': _counts(qs),
        'recent_leads': qs.order_by('-created_at')[:10],
        'project_manager': sp,
        'dashboard_type': 'project_manager',
    })


# ---------------------------------------------------------------------------
# Dashboard: Location Manager
# ---------------------------------------------------------------------------

@manager_required
def sales_dashboard_manager(request):
    qs = _lead_queryset(request.user)
    sp = _get_project_manager(request.user)

    # Team members at this location
    team = []
    if sp and sp.sales_point:
        team = list(
            ProjectManager.objects.filter(sales_point=sp.sales_point)
            .select_related('user', 'user__profile')
            .exclude(pk=sp.pk)
        )

    # Per-team-member lead counts
    team_stats = []
    for member in team:
        member_qs = LeadModel.objects.filter(assigned_user=member.user)
        team_stats.append({
            'project_manager': member,
            'counts': _counts(member_qs),
        })

    return render(request, 'sales/dashboard_manager.html', {
        'counts': _counts(qs),
        'recent_leads': qs.order_by('-created_at')[:10],
        'project_manager': sp,
        'team_stats': team_stats,
        'dashboard_type': 'manager',
    })


# ---------------------------------------------------------------------------
# Dashboard: Territory Manager
# ---------------------------------------------------------------------------

@territory_required
def sales_dashboard_territory(request):
    qs = _lead_queryset(request.user)
    sp = _get_project_manager(request.user)

    # Per-location stats
    location_stats = []
    for sales_point in SalesPoint.objects.filter(is_active=True).order_by('order', 'name'):
        sp_qs = LeadModel.objects.filter(sales_point=sales_point)
        location_stats.append({
            'sales_point': sales_point,
            'counts': _counts(sp_qs),
            'team_size': ProjectManager.objects.filter(
                sales_point=sales_point, status=ProjectManager.ACTIVE
            ).count(),
        })

    return render(request, 'sales/dashboard_territory.html', {
        'counts': _counts(qs),
        'recent_leads': qs.order_by('-created_at')[:15],
        'project_manager': sp,
        'location_stats': location_stats,
        'dashboard_type': 'territory',
    })


# ---------------------------------------------------------------------------
# Lead list — shared across all roles, filtered per role
# ---------------------------------------------------------------------------

@login_required
def sales_lead_list(request):
    qs = _lead_queryset(request.user)
    sp = _get_project_manager(request.user)

    # Filters
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    sales_point_id = request.GET.get('sales_point', '').strip()

    if q:
        qs = qs.filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(email__icontains=q)
            | Q(phone__icontains=q)
            | Q(zip_code__icontains=q)
        )
    if status:
        qs = qs.filter(status=status)

    # Location filter only available to managers/territory/staff
    can_filter_location = (
        request.user.is_staff or request.user.is_superuser
        or (sp and sp.role in (ProjectManager.LOCATION_MANAGER, ProjectManager.TERRITORY_MANAGER))
    )
    if sales_point_id and can_filter_location:
        qs = qs.filter(sales_point_id=sales_point_id)

    qs = qs.order_by('-created_at')
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    # Location dropdown only for those who can filter by location
    sales_points = []
    if can_filter_location:
        sales_points = SalesPoint.objects.filter(is_active=True).order_by('name')

    return render(request, 'sales/lead_list.html', {
        'page_obj': page_obj,
        'q': q,
        'status': status,
        'sales_point_id': sales_point_id,
        'sales_points': sales_points,
        'status_choices': LeadModel.STATUS_CHOICES,
        'project_manager': sp,
        'can_filter_location': can_filter_location,
    })


# ---------------------------------------------------------------------------
# Lead detail
# ---------------------------------------------------------------------------

@login_required
def sales_lead_detail(request, pk):
    lead = get_object_or_404(_lead_queryset(request.user), pk=pk)
    sp = _get_project_manager(request.user)

    if request.method == 'POST':
        form = LeadUpdateForm(request.POST, instance=lead)
        if form.is_valid():
            old_status = lead.status
            old_notes = lead.internal_notes
            updated = form.save()

            # ── Record activity for status change ──
            if updated.status != old_status:
                LeadActivity.objects.create(
                    lead=updated,
                    user=request.user,
                    action=LeadActivity.ACTION_STATUS,
                    detail=(
                        f"Status changed from '{lead.get_status_display()}' "
                        f"to '{updated.get_status_display()}'."
                    ),
                )

            # ── Record activity for notes update ──
            if updated.internal_notes != old_notes:
                LeadActivity.objects.create(
                    lead=updated,
                    user=request.user,
                    action=LeadActivity.ACTION_NOTES,
                    detail="Internal notes updated.",
                )

            return redirect('sales_lead_detail', pk=pk)
    else:
        form = LeadUpdateForm(instance=lead)

    activities = lead.activities.select_related('user', 'user__profile').order_by('-created_at')[:20]

    return render(request, 'sales/lead_detail.html', {
        'lead': lead,
        'form': form,
        'project_manager': sp,
        'activities': activities,
    })









# ── ADD to the bottom of home/views_sales.py ────────────────────────────────
# Also add ManualLeadForm to the import at the top:
#   from .forms import LeadUpdateForm, ManualLeadForm

from django.contrib import messages as django_messages


@login_required
def sales_lead_create(request):
    """Manually create a lead from inside the CRM."""
    from .forms import ManualLeadForm

    sp = _get_project_manager(request.user)

    if request.method == 'POST':
        form = ManualLeadForm(request.POST, user=request.user)
        if form.is_valid():
            lead = form.save(commit=False)

            # If sales_point was disabled (locked to user's location), set it manually
            if not lead.sales_point and sp and sp.sales_point:
                lead.sales_point = sp.sales_point

            # Auto-assign to current user if no one assigned
            if not lead.assigned_user:
                lead.assigned_user = request.user

            # If no source_page provided, mark as manually entered
            if not lead.source_page:
                lead.source_page = f'Manual entry by {request.user.get_full_name()}'

            lead.save()
            form.save_m2m()

            django_messages.success(request, f'Lead for {lead.first_name} {lead.last_name} created successfully.')
            return redirect('sales_lead_detail', pk=lead.pk)
        else:
            django_messages.error(request, 'Please correct the errors below.')
    else:
        # Pre-fill sales_point and assigned_user for project managers
        initial = {}
        if sp and sp.sales_point:
            initial['sales_point'] = sp.sales_point
        initial['assigned_user'] = request.user
        initial['status'] = 'new'
        form = ManualLeadForm(user=request.user, initial=initial)

    return render(request, 'sales/lead_create.html', {
        'form': form,
        'project_manager': sp,
    })

# ---------------------------------------------------------------------------
# Estimate: create / edit
# ---------------------------------------------------------------------------

import json
from decimal import Decimal, InvalidOperation

from .models import Estimate, EstimateLineItem


@login_required
def estimate_edit(request, lead_pk, pk=None):
    """
    pk=None  → create a new estimate for the lead
    pk=<int> → edit an existing estimate
    """
    lead = get_object_or_404(_lead_queryset(request.user), pk=lead_pk)

    if pk:
        estimate = get_object_or_404(Estimate, pk=pk, lead=lead)
    else:
        estimate = None

    if request.method == 'POST':
        # --- parse scalars ---
        status   = request.POST.get('status', 'draft')
        notes    = request.POST.get('notes', '').strip()
        try:
            tax_rate = Decimal(request.POST.get('tax_rate', '0') or '0')
        except InvalidOperation:
            tax_rate = Decimal('0')

        if estimate is None:
            estimate = Estimate.objects.create(
                lead=lead,
                created_by=request.user,
                status=status,
                notes=notes,
                tax_rate=tax_rate,
            )
        else:
            estimate.status   = status
            estimate.notes    = notes
            estimate.tax_rate = tax_rate
            estimate.save()

        # --- parse line items sent as parallel lists ---
        descs  = request.POST.getlist('item_desc')
        qtys   = request.POST.getlist('item_qty')
        prices = request.POST.getlist('item_price')

        estimate.line_items.all().delete()
        for i, desc in enumerate(descs):
            desc = desc.strip()
            if not desc:
                continue
            try:
                qty   = Decimal(qtys[i]   or '1')
            except (InvalidOperation, IndexError):
                qty = Decimal('1')
            try:
                price = Decimal(prices[i] or '0')
            except (InvalidOperation, IndexError):
                price = Decimal('0')
            EstimateLineItem.objects.create(
                estimate=estimate,
                description=desc,
                quantity=qty,
                unit_price=price,
                order=i,
            )

        return redirect('estimate_edit', lead_pk=lead_pk, pk=estimate.pk)

    return render(request, 'sales/estimate_edit.html', {
        'lead': lead,
        'estimate': estimate,
        'status_choices': Estimate.STATUS_CHOICES,
    })
