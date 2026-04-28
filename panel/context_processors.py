from account.models import ProjectManager
from home.models import LeadModel


def _new_leads_qs_for(user):
    qs = LeadModel.objects.filter(status="new")
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


def new_leads_badge(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"new_leads_count": 0}
    return {"new_leads_count": _new_leads_qs_for(user).count()}
