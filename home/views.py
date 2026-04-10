# home/views.py

import logging

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import TemplateView
from django.urls import reverse

from .forms import LeadForm
from .models import (
    Gallery,
    LeadActivity,
    LeadAttachment,
    Testimonial,
    VideoReview,
    SalesPoint,
    ServiceCity,
    ZipCode,
    LeadModel,
)
from .notifications import (
    notify_new_lead_to_customer,
    notify_new_lead_to_salesperson,
    notify_new_lead_to_location,
)
from .geo import auto_set_location

logger = logging.getLogger(__name__)


def home(request):
    MAX_TESTIMONIALS = 6

    # Auto-detect visitor location via IP (only on first visit, won't override manual pick)
    auto_detected = auto_set_location(request)

    featured = Testimonial.objects.filter(is_active=True, is_featured=True).order_by("order")
    others = Testimonial.objects.filter(is_active=True, is_featured=False).order_by("order")
    testimonials = (list(featured) + list(others))[:MAX_TESTIMONIALS]

    selected_sales_point = None
    selected_slug = request.session.get("selected_sales_point_slug")
    if selected_slug:
        selected_sales_point = SalesPoint.objects.filter(slug=selected_slug, is_active=True).first()

    if selected_sales_point:
        consultation_url = f"{reverse('create_lead')}?sales_point={selected_sales_point.slug}"
    else:
        consultation_url = reverse("create_lead")

    return render(request, "home/home.html", {
        "testimonials": testimonials,
        "selected_city": selected_sales_point,
        "consultation_url": consultation_url,
        "location_auto_detected": bool(auto_detected),
    })


def galleries(request):
    gallery_list = Gallery.objects.filter(is_active=True).prefetch_related("items")
    return render(request, "home/gallery.html", {"galleries": gallery_list})


def gallery_detail(request, slug):
    gallery = get_object_or_404(
        Gallery.objects.filter(is_active=True).prefetch_related("items"),
        slug=slug,
    )
    items = list(gallery.items.all())
    return render(request, "home/gallery_detail.html", {"gallery": gallery, "items": items})


def locations_list(request):
    sales_points = SalesPoint.objects.filter(is_active=True).order_by("order", "name")
    return render(request, "home/locations.html", {"sales_points": sales_points})


def location_detail(request, slug):
    sales_point = get_object_or_404(SalesPoint, slug=slug, is_active=True)
    galleries = sales_point.galleries.filter(is_active=True).prefetch_related("items").order_by("order", "name")[:12]
    cities = sales_point.cities.filter(is_active=True).prefetch_related("zip_codes").order_by("order", "name")

    request.session["selected_sales_point_slug"] = sales_point.slug

    return render(request, "home/location_detail.html", {
        "sales_point": sales_point,
        "galleries": galleries,
        "cities": cities,
        "city": sales_point,
    })


def set_location(request, slug):
    sales_point = get_object_or_404(SalesPoint, slug=slug, is_active=True)
    request.session["selected_sales_point_slug"] = sales_point.slug
    request.session["location_auto_detected"] = False   # hide banner after manual pick/dismiss
    next_url = request.GET.get("next") or reverse("location_detail", args=[sales_point.slug])
    return redirect(next_url)


class Service(TemplateView):
    template_name = "home/service.html"


class Product(TemplateView):
    template_name = "home/product.html"


class About(TemplateView):
    template_name = "home/about.html"


class Video(TemplateView):
    template_name = "home/video.html"


def videoreviews(request):
    featured = VideoReview.objects.filter(is_active=True, is_featured=True).order_by("order", "-created_at")
    qs = VideoReview.objects.filter(is_active=True, is_featured=False).order_by("order", "-created_at")
    paginator = Paginator(qs, 6)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return render(request, "home/partials/_video_cards.html", {"page_obj": page_obj})

    return render(request, "home/videoreviews.html", {
        "featured": featured,
        "page_obj": page_obj,
    })


def create_lead(request):
    selected_sales_point = None
    sales_point_slug = request.GET.get("sales_point") or request.session.get("selected_sales_point_slug")

    if sales_point_slug:
        selected_sales_point = SalesPoint.objects.filter(slug=sales_point_slug, is_active=True).first()

    if request.method == "POST":
        lead_form = LeadForm(request.POST, request.FILES)

        if lead_form.is_valid():
            lead = lead_form.save(commit=False)

            # ── Route lead to the right sales point via ZIP code ──
            submitted_zip = (lead.zip_code or "").strip()
            matched_zip = ZipCode.objects.select_related(
                "service_city",
                "service_city__sales_point",
                "service_city__sales_point__assigned_user",
            ).filter(
                code=submitted_zip,
                service_city__is_active=True,
                service_city__sales_point__is_active=True,
            ).first()

            if matched_zip:
                lead.service_city = matched_zip.service_city
                lead.sales_point = matched_zip.service_city.sales_point
                lead.assigned_user = matched_zip.service_city.sales_point.assigned_user
            elif selected_sales_point:
                lead.sales_point = selected_sales_point
                lead.assigned_user = selected_sales_point.assigned_user

            lead.source_page = request.META.get("HTTP_REFERER", "")
            lead.save()
            lead_form.save_m2m()

            # ── Save attachments ──
            uploaded_files = lead_form.cleaned_data.get("attachments") or []
            attachment_names = []
            for f in uploaded_files:
                try:
                    LeadAttachment.objects.create(lead=lead, file=f)
                    attachment_names.append(f.name)
                except Exception:
                    logger.exception("Failed to save attachment %s for lead %s", f.name, lead.pk)

            # ── Audit log ──
            LeadActivity.objects.create(
                lead=lead,
                user=None,
                action=LeadActivity.ACTION_CREATED,
                detail=(
                    f"New lead from {lead.first_name} {lead.last_name} "
                    f"({lead.zip_code}) via website."
                ),
            )

            # ── Notifications (all failures are caught internally) ──
            notify_new_lead_to_customer(lead)
            notify_new_lead_to_salesperson(lead)
            notify_new_lead_to_location(lead, attachment_names=attachment_names)

            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"redirect_url": reverse("create_lead_success")})
            return redirect("create_lead_success")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        lead_form = LeadForm()

    return render(request, "home/create_lead.html", {
        "lead_form": lead_form,
        "selected_sales_point": selected_sales_point,
        "selected_city": selected_sales_point,
    })


def create_lead_success(request):
    return render(request, "home/createlead_success.html")


class CopyrightPage(TemplateView):
    template_name = "home/copyright.html"


class Terms(TemplateView):
    template_name = "home/terms.html"


class Privacy(TemplateView):
    template_name = "home/privacy.html"


class GarageCabinet(TemplateView):
    template_name = "home/garage_cabinet.html"


class GarageFlooring(TemplateView):
    template_name = "home/garage_flooring.html"


class GarageSlatwall(TemplateView):
    template_name = "home/garage_slatwall.html"


class StorageRack(TemplateView):
    template_name = "home/storage_rack.html"


class GarageMakeover(TemplateView):
    template_name = "home/garage_makeover.html"


class GarageDoor(TemplateView):
    template_name = "home/garage_door.html"


class GarageConversion(TemplateView):
    template_name = "home/garage_conversion.html"


class CarLift(TemplateView):
    template_name = "home/car_lift.html"