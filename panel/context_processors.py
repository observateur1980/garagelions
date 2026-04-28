from account.models import ProjectManager
from home.models import LeadModel, LeadFollowUp


def _visible_leads_qs(user):
    """Leads scoped by role (matches panel.views._lead_queryset)."""
    qs = LeadModel.objects.all()
    if user.is_superuser or user.is_staff:
        return qs
    try:
        pm = user.project_manager
    except ProjectManager.DoesNotExist:
        pm = None
    if pm is None:
        return qs.filter(assigned_user=user)
    if pm.role == ProjectManager.TERRITORY_MANAGER:
        return qs
    if pm.role == ProjectManager.LOCATION_MANAGER:
        managed = list(pm.extra_sales_points.values_list("pk", flat=True))
        if pm.sales_point_id:
            managed.append(pm.sales_point_id)
        if managed:
            return qs.filter(sales_point_id__in=managed)
        return qs.none()
    return qs.filter(assigned_user=user)


def _new_leads_qs_for(user):
    return _visible_leads_qs(user).filter(status="new")


def new_leads_badge(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"new_leads_count": 0, "followup_attention_count": 0}
    visible_lead_ids = _visible_leads_qs(user).values_list("pk", flat=True)
    return {
        "new_leads_count": _new_leads_qs_for(user).count(),
        "followup_attention_count": LeadFollowUp.objects.filter(
            lead_id__in=visible_lead_ids,
            is_sent=True,
            acknowledged_at__isnull=True,
        ).count(),
    }
