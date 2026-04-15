from django.conf import settings
from .models import SalesPoint, VideoReview


def footer_video_reviews(request):
    return {
        "footer_video_reviews": VideoReview.objects.filter(
            is_active=True
        ).order_by("-created_at")[:2]
    }


def selected_city(request):
    slug = request.session.get("selected_sales_point_slug")
    sales_point = None

    if slug:
        sales_point = SalesPoint.objects.filter(slug=slug, is_active=True).first()

    return {
        "selected_city": sales_point,
        "company_toll_free": getattr(settings, "COMPANY_TOLL_FREE", "+18554645119"),
        "company_toll_free_display": getattr(settings, "COMPANY_TOLL_FREE_DISPLAY", "1-855-464-5119"),
    }