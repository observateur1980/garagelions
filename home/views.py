# home/views.py

import logging
import math

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
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
    notify_new_lead_to_project_manager,
    notify_new_lead_to_location,
    notify_unassigned_lead,
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
    sales_points = SalesPoint.objects.filter(is_active=True).prefetch_related("cities").order_by("order", "name")
    return render(request, "home/locations.html", {"sales_points": sales_points})


def location_detail(request, slug):
    sales_point = get_object_or_404(SalesPoint, slug=slug, is_active=True)
    galleries = sales_point.galleries.filter(is_active=True).prefetch_related("items").order_by("order", "name")[:12]
    cities = sales_point.cities.filter(is_active=True).prefetch_related("zip_codes").order_by("order", "name")

    request.session["selected_sales_point_slug"] = sales_point.slug

    default_services = [
        {"name": "Garage Makeovers",  "icon": "&#127968;", "url": "/garage_makeover"},
        {"name": "Garage Cabinets",   "icon": "&#128736;", "url": "/garage_cabinet"},
        {"name": "Garage Flooring",   "icon": "&#11035;",  "url": "/garage_flooring"},
        {"name": "Slatwall Solutions","icon": "&#128295;", "url": "/garage_slatwall"},
        {"name": "Storage Racks",     "icon": "&#128584;", "url": "/storage_rack"},
        {"name": "Garage Doors",      "icon": "&#127968;", "url": "/garage_door"},
        {"name": "Garage Conversion", "icon": "&#128188;", "url": "/garage_conversion"},
        {"name": "Car Lifts",         "icon": "&#128665;", "url": "/car_lift"},
    ]

    # Build a map search query from service area cities (for service-area map)
    city_names = [f"{c.name}, {c.state}" for c in cities]
    map_query = " | ".join(city_names[:6]) if city_names else (
        sales_point.full_address or sales_point.name
    )

    return render(request, "home/location_detail.html", {
        "sales_point": sales_point,
        "galleries": galleries,
        "cities": cities,
        "city": sales_point,
        "default_services": default_services,
        "map_query": map_query,
        "map_center_city": city_names[0] if city_names else None,
    })


def set_location(request, slug):
    sales_point = get_object_or_404(SalesPoint, slug=slug, is_active=True)
    request.session["selected_sales_point_slug"] = sales_point.slug
    request.session["location_auto_detected"] = False   # hide banner after manual pick/dismiss
    next_url = request.GET.get("next") or reverse("location_detail", args=[sales_point.slug])
    return redirect(next_url)


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


@require_POST
def set_location_by_coords(request):
    """
    Called by the browser after the user grants geolocation permission.
    Finds the nearest SalesPoint by:
      1. Distance (lat/lng) — for sales points that have coordinates set
      2. ZIP code reverse-lookup via ip-api — fallback when lat/lng is missing
    """
    try:
        lat = float(request.POST.get("lat", ""))
        lng = float(request.POST.get("lng", ""))
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "invalid coords"}, status=400)

    # Only set if the user hasn't already picked a location manually
    if request.session.get("selected_sales_point_slug"):
        return JsonResponse({"ok": True, "already_set": True})

    # ── Pass 1: distance match for sales points that have lat/lng ────────────
    candidates = SalesPoint.objects.filter(
        is_active=True,
        latitude__isnull=False,
        longitude__isnull=False,
    )

    nearest = None
    nearest_km = None
    for sp in candidates:
        km = _haversine_km(lat, lng, float(sp.latitude), float(sp.longitude))
        if nearest_km is None or km < nearest_km:
            nearest = sp
            nearest_km = km

    MAX_KM = 200
    if nearest and nearest_km <= MAX_KM:
        request.session["selected_sales_point_slug"] = nearest.slug
        request.session["location_auto_detected"] = True
        return JsonResponse({"ok": True, "slug": nearest.slug, "name": nearest.name})

    # ── Pass 2: ZIP/city fallback via the visitor's IP ───────────────────────
    # Useful when lat/lng is not filled in on some SalesPoint records
    from .geo import detect_sales_point
    sales_point = detect_sales_point(request)
    if sales_point:
        request.session["selected_sales_point_slug"] = sales_point.slug
        request.session["location_auto_detected"] = True
        return JsonResponse({"ok": True, "slug": sales_point.slug, "name": sales_point.name})

    return JsonResponse({"ok": False, "reason": "no_coverage"})


def geo_debug(request):
    """Temporary debug view — remove after troubleshooting."""
    from .geo import _get_client_ip, _lookup_ip, detect_sales_point
    ip = _get_client_ip(request)
    geo = _lookup_ip(ip)

    zip_match = None
    city_match = None
    if geo:
        zip_match = ZipCode.objects.select_related(
            "service_city__sales_point"
        ).filter(code=geo["zip"]).first()

        city_match = ServiceCity.objects.select_related("sales_point").filter(
            name__iexact=geo["city"]
        ).first()

    detected_sp = detect_sales_point(request)
    session_slug = request.session.get("selected_sales_point_slug")

    return JsonResponse({
        "ip": ip,
        "geo": geo,
        "session_slug": session_slug,
        "zip_match": str(zip_match) if zip_match else None,
        "zip_match_sales_point": str(zip_match.service_city.sales_point) if zip_match else None,
        "city_match": str(city_match) if city_match else None,
        "city_match_sales_point": str(city_match.sales_point) if city_match else None,
        "detected_sales_point": str(detected_sp) if detected_sp else None,
    })


def geo_reset(request):
    """Clears location from session so detection runs fresh."""
    request.session.pop("selected_sales_point_slug", None)
    request.session.pop("location_auto_detected", None)
    return JsonResponse({"ok": True, "message": "Session location cleared. Reload the home page."})


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
            notify_new_lead_to_project_manager(lead)
            notify_new_lead_to_location(lead, attachment_names=attachment_names)
            if not lead.assigned_user:
                notify_unassigned_lead(lead)

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


def cabinet_designer(request):
    return render(request, "home/cabinet_designer.html")


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


# ── PWA: manifest + service worker ──────────────────────────────────────
PWA_MANIFEST = {
    "name": "Garage Lions Leads",
    "short_name": "GL Leads",
    "description": "Garage Lions mobile leads app",
    "start_url": "/panel/m/leads/",
    "scope": "/panel/m/",
    "display": "standalone",
    "orientation": "portrait",
    "background_color": "#f3f4f6",
    "theme_color": "#374151",
    "icons": [
        {"src": "/static/icons/pwa-icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
        {"src": "/static/icons/pwa-icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
    ],
}

PWA_SERVICE_WORKER_JS = """\
// Garage Lions Leads PWA service worker
const CACHE = "gl-leads-v1";
const SHELL = ["/static/icons/apple-touch-icon.png",
               "/static/icons/pwa-icon-192.png",
               "/static/icons/pwa-icon-512.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Network-first for HTML/JSON, cache-first for static assets.
self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  const isStatic = url.pathname.startsWith("/static/") || url.pathname.startsWith("/media/");

  if (isStatic) {
    event.respondWith(
      caches.match(req).then((cached) =>
        cached ||
        fetch(req).then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
          return res;
        })
      )
    );
    return;
  }

  // For navigations, fall back to the leads list when offline.
  event.respondWith(
    fetch(req).catch(() => caches.match("/panel/leads/") || new Response("Offline", { status: 503 }))
  );
});
"""


def pwa_manifest(request):
    return JsonResponse(PWA_MANIFEST, json_dumps_params={"indent": 2})


def pwa_service_worker(request):
    response = HttpResponse(PWA_SERVICE_WORKER_JS, content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response