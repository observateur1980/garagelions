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

    all_cities = SalesPoint.objects.filter(is_active=True).order_by("order", "name")

    return {
        "selected_city": sales_point,   # keep old template variable name so navbar keeps working
        "all_cities": all_cities,       # keep old template variable name too
    }