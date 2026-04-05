import smtplib

from django.conf import settings
from django.contrib import messages
from django.core.mail import EmailMessage
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import TemplateView
from django.urls import reverse

from .forms import LeadForm
from .models import (
    Gallery,
    LeadAttachment,
    Testimonial,
    VideoReview,
    SalesPoint,
    ServiceCity,
    ZipCode,
    LeadModel,
)


def home(request):
    MAX_TESTIMONIALS = 6

    featured = Testimonial.objects.filter(
        is_active=True,
        is_featured=True
    ).order_by("order")

    others = Testimonial.objects.filter(
        is_active=True,
        is_featured=False
    ).order_by("order")

    testimonials = list(featured) + list(others)
    testimonials = testimonials[:MAX_TESTIMONIALS]

    selected_sales_point = None
    selected_slug = request.session.get("selected_sales_point_slug")

    if selected_slug:
        selected_sales_point = SalesPoint.objects.filter(
            slug=selected_slug,
            is_active=True
        ).first()

    if selected_sales_point:
        consultation_url = f"{reverse('create_lead')}?sales_point={selected_sales_point.slug}"
    else:
        consultation_url = reverse("create_lead")

    return render(request, "home/home.html", {
        "testimonials": testimonials,
        "selected_city": selected_sales_point,
        "consultation_url": consultation_url,
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
        "city": sales_point,   # keeps current template compatibility where needed
    })


def set_location(request, slug):
    sales_point = get_object_or_404(SalesPoint, slug=slug, is_active=True)
    request.session["selected_sales_point_slug"] = sales_point.slug
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
            consultation_request = lead_form.save(commit=False)

            submitted_zip = (consultation_request.zip_code or "").strip()

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
                consultation_request.service_city = matched_zip.service_city
                consultation_request.sales_point = matched_zip.service_city.sales_point
                consultation_request.assigned_user = matched_zip.service_city.sales_point.assigned_user
                consultation_request.assigned_to = (
                    matched_zip.service_city.sales_point.assigned_salesperson or ""
                )
            elif selected_sales_point:
                consultation_request.sales_point = selected_sales_point
                consultation_request.assigned_user = selected_sales_point.assigned_user
                consultation_request.assigned_to = selected_sales_point.assigned_salesperson or ""

            consultation_request.source_page = request.META.get("HTTP_REFERER", "")
            consultation_request.save()
            lead_form.save_m2m()

            uploaded_files = lead_form.cleaned_data.get("attachments") or []
            for f in uploaded_files:
                LeadAttachment.objects.create(lead=consultation_request, file=f)

            consultation_types_display = ", ".join(consultation_request.consultation_types) if consultation_request.consultation_types else ""
            attachment_names = [f.name for f in uploaded_files]
            attachments_text = (
                "\n\nAttachments:\n" + "\n".join(f"- {n}" for n in attachment_names)
            ) if attachment_names else ""

            sales_point_text = str(consultation_request.sales_point) if consultation_request.sales_point else "No sales point matched"
            city_text = str(consultation_request.service_city) if consultation_request.service_city else "No city matched"
            assigned_text = consultation_request.assigned_to or "Not assigned"

            full_message = (
                f"First Name: {consultation_request.first_name}\n"
                f"Last Name: {consultation_request.last_name}\n"
                f"Email: {consultation_request.email}\n"
                f"Phone: {consultation_request.phone}\n"
                f"ZIP Code: {consultation_request.zip_code}\n"
                f"Sales Point: {sales_point_text}\n"
                f"Service City: {city_text}\n"
                f"Assigned To: {assigned_text}\n"
                f"Consultation Types: {consultation_types_display}\n\n"
                f"Message:\n{consultation_request.message}"
            ) + attachments_text

            recipient_list = ["info@garagelions.com"]
            from_email = settings.DEFAULT_FROM_EMAIL
            reply_to = []

            if consultation_request.sales_point:
                if consultation_request.sales_point.lead_notification_email:
                    recipient_list = [consultation_request.sales_point.lead_notification_email]

                if consultation_request.sales_point.from_email:
                    from_email = consultation_request.sales_point.from_email

                if consultation_request.sales_point.reply_to_email:
                    reply_to = [consultation_request.sales_point.reply_to_email]

            try:
                email_message = EmailMessage(
                    subject=f"Garage Lions Consultation - {consultation_request.first_name} {consultation_request.last_name}",
                    body=full_message,
                    from_email=from_email,
                    to=recipient_list,
                    reply_to=reply_to,
                )
                email_message.send(fail_silently=False)
                return redirect("create_lead_success")
            except smtplib.SMTPException:
                messages.error(request, "There was an error sending your request. Please try again later.")
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