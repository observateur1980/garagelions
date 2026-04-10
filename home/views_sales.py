# home/views_sales.py
#
# Three separate dashboards, one lead list, one lead detail.
# Access is gated by the Salesperson.role field.
# Superusers and is_staff users always see everything.

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from account.models import Salesperson
from .forms import LeadUpdateForm
from .models import LeadActivity, LeadModel, SalesPoint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_salesperson(user):
    """Return the Salesperson record or None."""
    try:
        return user.salesperson
    except Salesperson.DoesNotExist:
        return None


def _lead_queryset(user):
    """
    Return the base LeadModel queryset scoped to what this user may see.

    - Superuser / is_staff         → all leads
    - Territory Manager            → all leads (across all locations)
    - Location Manager             → all leads for their SalesPoint
    - Salesperson                  → only leads assigned to them
    - No Salesperson record        → only leads assigned to them (fallback)
    """
    qs = LeadModel.objects.select_related(
        'sales_point', 'service_city', 'assigned_user', 'assigned_user__profile'
    )

    if user.is_superuser or user.is_staff:
        return qs

    sp = _get_salesperson(user)
    if sp is None:
        return qs.filter(assigned_user=user)

    if sp.role == Salesperson.TERRITORY_MANAGER:
        return qs

    if sp.role == Salesperson.LOCATION_MANAGER:
        if sp.sales_point:
            return qs.filter(sales_point=sp.sales_point)
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

def salesperson_required(view_func):
    """User must be logged in AND have a Salesperson record (or be staff)."""
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.is_staff or request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        sp = _get_salesperson(request.user)
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
        sp = _get_salesperson(request.user)
        if sp and sp.role in (Salesperson.LOCATION_MANAGER, Salesperson.TERRITORY_MANAGER):
            return view_func(request, *args, **kwargs)
        return redirect('sales_dashboard')
    return wrapper


def territory_required(view_func):
    """User must be a Territory Manager or staff/superuser."""
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.is_staff or request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        sp = _get_salesperson(request.user)
        if sp and sp.role == Salesperson.TERRITORY_MANAGER:
            return view_func(request, *args, **kwargs)
        return redirect('sales_dashboard')
    return wrapper


# ---------------------------------------------------------------------------
# Dashboard: Salesperson (default)
# ---------------------------------------------------------------------------

@login_required
def sales_dashboard(request):
    qs = _lead_queryset(request.user)
    sp = _get_salesperson(request.user)

    return render(request, 'sales/dashboard.html', {
        'counts': _counts(qs),
        'recent_leads': qs.order_by('-created_at')[:10],
        'salesperson': sp,
        'dashboard_type': 'salesperson',
    })


# ---------------------------------------------------------------------------
# Dashboard: Location Manager
# ---------------------------------------------------------------------------

@manager_required
def sales_dashboard_manager(request):
    qs = _lead_queryset(request.user)
    sp = _get_salesperson(request.user)

    # Team members at this location
    team = []
    if sp and sp.sales_point:
        team = list(
            Salesperson.objects.filter(sales_point=sp.sales_point)
            .select_related('user', 'user__profile')
            .exclude(pk=sp.pk)
        )

    # Per-team-member lead counts
    team_stats = []
    for member in team:
        member_qs = LeadModel.objects.filter(assigned_user=member.user)
        team_stats.append({
            'salesperson': member,
            'counts': _counts(member_qs),
        })

    return render(request, 'sales/dashboard_manager.html', {
        'counts': _counts(qs),
        'recent_leads': qs.order_by('-created_at')[:10],
        'salesperson': sp,
        'team_stats': team_stats,
        'dashboard_type': 'manager',
    })


# ---------------------------------------------------------------------------
# Dashboard: Territory Manager
# ---------------------------------------------------------------------------

@territory_required
def sales_dashboard_territory(request):
    qs = _lead_queryset(request.user)
    sp = _get_salesperson(request.user)

    # Per-location stats
    location_stats = []
    for sales_point in SalesPoint.objects.filter(is_active=True).order_by('order', 'name'):
        sp_qs = LeadModel.objects.filter(sales_point=sales_point)
        location_stats.append({
            'sales_point': sales_point,
            'counts': _counts(sp_qs),
            'team_size': Salesperson.objects.filter(
                sales_point=sales_point, status=Salesperson.ACTIVE
            ).count(),
        })

    return render(request, 'sales/dashboard_territory.html', {
        'counts': _counts(qs),
        'recent_leads': qs.order_by('-created_at')[:15],
        'salesperson': sp,
        'location_stats': location_stats,
        'dashboard_type': 'territory',
    })


# ---------------------------------------------------------------------------
# Lead list — shared across all roles, filtered per role
# ---------------------------------------------------------------------------

@login_required
def sales_lead_list(request):
    qs = _lead_queryset(request.user)
    sp = _get_salesperson(request.user)

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
        or (sp and sp.role in (Salesperson.LOCATION_MANAGER, Salesperson.TERRITORY_MANAGER))
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
        'salesperson': sp,
        'can_filter_location': can_filter_location,
    })


# ---------------------------------------------------------------------------
# Lead detail
# ---------------------------------------------------------------------------

@login_required
def sales_lead_detail(request, pk):
    lead = get_object_or_404(_lead_queryset(request.user), pk=pk)
    sp = _get_salesperson(request.user)

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
        'salesperson': sp,
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

    sp = _get_salesperson(request.user)

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
        # Pre-fill sales_point and assigned_user for salespeople
        initial = {}
        if sp and sp.sales_point:
            initial['sales_point'] = sp.sales_point
        initial['assigned_user'] = request.user
        initial['status'] = 'new'
        form = ManualLeadForm(user=request.user, initial=initial)

    return render(request, 'sales/lead_create.html', {
        'form': form,
        'salesperson': sp,
    })