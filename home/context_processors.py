from .models import VideoReview

def footer_video_reviews(request):
    return {
        "footer_video_reviews": VideoReview.objects.filter(
            is_active=True
        ).order_by("-created_at")[:2]
    }