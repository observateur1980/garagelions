# home/admin.py — COMPLETE FILE (replace your existing one)

import csv
import io
import re

from django.contrib import admin, messages
from django.db import models
from django.shortcuts import redirect, render
from django.urls import path
from django.utils.html import format_html
from django.utils.timezone import now
from datetime import timedelta

from .models import (
    SalesPoint,
    SalesPointWorkingHour,
    ZipCode,
    Gallery,
    GalleryItem,
    Testimonial,
    LeadModel,
    LeadActivity,
    LeadAttachment,
    VideoReview,
    ServiceCity,
    FranchiseAgreement,
)


# ── Inlines ──────────────────────────────────────────────────────────────

class ZipCodeInline(admin.TabularInline):
    model = ZipCode
    extra = 1


class SalesPointWorkingHourInline(admin.TabularInline):
    model = SalesPointWorkingHour
    extra = 0
    fields = ("day", "is_open", "open_time", "close_time", "note")


class FranchiseAgreementInline(admin.StackedInline):
    model = FranchiseAgreement
    extra = 0
    fields = (
        "franchisee_legal_name", "franchisee_contact_name",
        "franchisee_email", "franchisee_phone",
        "status", "upfront_fee", "royalty_rate", "marketing_fee_rate",
        "agreement_date", "start_date", "expiry_date", "renewal_date",
        "territory_notes", "agreement_document", "internal_notes",
    )


class GalleryItemInline(admin.StackedInline):
    model = GalleryItem
    extra = 1
    ordering = ("sort_order", "id")
    fields = (
        "sort_order", "media_type", "file", "thumbnail",
        "title", "section_heading", "text_before", "text_after",
    )


class LeadAttachmentInline(admin.TabularInline):
    model = LeadAttachment
    extra = 0
    readonly_fields = ("uploaded_at",)


class LeadActivityInline(admin.TabularInline):
    model = LeadActivity
    extra = 0
    readonly_fields = ("created_at", "user", "action", "detail")
    fields = ("created_at", "user", "action", "detail")
    ordering = ("-created_at",)
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


# ── ServiceCity ───────────────────────────────────────────────────────────

@admin.register(ServiceCity)
class ServiceCityAdmin(admin.ModelAdmin):
    list_display = ("name", "state", "sales_point", "active_toggle", "order")
    list_filter = ("sales_point", "state", "is_active")
    search_fields = ("name", "state", "sales_point__name")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ZipCodeInline]

    fieldsets = (
        ("City", {
            "fields": ("name", "slug", "state", "is_active", "order")
        }),
        ("Sales Point (optional)", {
            "fields": ("sales_point",),
            "description": "Assign this city to a sales point. Leave blank to assign later.",
        }),
    )

    def get_urls(self):
        urls = super().get_urls()
        extra = [
            path(
                "<int:pk>/toggle-active/",
                self.admin_site.admin_view(self.toggle_active_view),
                name="home_servicecity_toggle_active",
            ),
            path(
                "import-csv/",
                self.admin_site.admin_view(self.import_csv_view),
                name="home_servicecity_import_csv",
            ),
        ]
        return extra + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["import_csv_url"] = "import-csv/"
        return super().changelist_view(request, extra_context=extra_context)

    def toggle_active_view(self, request, pk):
        city = ServiceCity.objects.get(pk=pk)
        city.is_active = not city.is_active
        city.save(update_fields=["is_active"])
        return redirect(request.META.get("HTTP_REFERER", ".."))

    def active_toggle(self, obj):
        if obj.is_active:
            label, color = "Active", "#28a745"
        else:
            label, color = "Inactive", "#dc3545"
        return format_html(
            '<a href="{}" style="'
            'display:inline-block;padding:2px 10px;border-radius:4px;'
            'background:{};color:#fff;text-decoration:none;font-size:12px;'
            'font-weight:600;">{}</a>',
            f"{obj.pk}/toggle-active/",
            color,
            label,
        )
    active_toggle.short_description = "Active"

    def import_csv_view(self, request):
        if request.method == "POST":
            csv_file = request.FILES.get("csv_file")
            if not csv_file or not csv_file.name.endswith(".csv"):
                messages.error(request, "Please upload a valid .csv file.")
                return redirect(".")

            created_cities = created_zips = 0
            errors = []

            text = io.TextIOWrapper(csv_file, encoding="utf-8-sig")
            reader = csv.DictReader(text)

            for i, row in enumerate(reader, start=2):
                try:
                    city, city_created = ServiceCity.objects.get_or_create(
                        name=row["city_name"].strip(),
                        state=row["state"].strip(),
                        defaults={"is_active": True},
                    )
                    if city_created:
                        created_cities += 1

                    _, zip_created = ZipCode.objects.get_or_create(
                        code=row["zip_code"].strip(),
                        defaults={"service_city": city},
                    )
                    if zip_created:
                        created_zips += 1

                except Exception as e:
                    errors.append(f"Row {i}: {e}")

            if errors:
                for err in errors[:10]:
                    messages.warning(request, err)

            messages.success(
                request,
                f"Import complete — Cities: {created_cities}, ZIPs: {created_zips}",
            )
            return redirect("..")

        context = {
            **self.admin_site.each_context(request),
            "title": "Import cities & ZIP codes from CSV",
            "opts": self.model._meta,
        }
        return render(request, "admin/home/servicecity/import_csv.html", context)


# ── ZipCode ───────────────────────────────────────────────────────────────

@admin.register(ZipCode)
class ZipCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "service_city", "sales_point_name")
    search_fields = ("code", "service_city__name", "service_city__sales_point__name")

    def sales_point_name(self, obj):
        sp = obj.service_city.sales_point if obj.service_city else None
        return sp.name if sp else "-"
    sales_point_name.short_description = "Sales Point"


# ── SalesPoint ────────────────────────────────────────────────────────────

@admin.register(SalesPoint)
class SalesPointAdmin(admin.ModelAdmin):
    list_display = (
        "name", "location_type", "local_phone", "local_email",
        "assigned_user", "is_active", "is_featured", "order",
        "related_cities", "manage_territory_link",
    )
    list_editable = ("is_active", "is_featured", "order")
    list_filter = ("location_type", "is_active", "is_featured")
    search_fields = ("name", "local_email", "lead_notification_email")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [SalesPointWorkingHourInline, FranchiseAgreementInline]
    readonly_fields = ("zip_codes_preview",)

    fieldsets = (
        ("Basic", {
            "fields": (
                "name", "slug", "location_type", "royalty_rate",
                "is_active", "is_featured", "order",
            )
        }),
        ("SEO", {
            "fields": ("page_title", "meta_description", "hero_title", "hero_subtitle")
        }),
        ("Address", {
            "fields": ("address_line_1", "address_line_2", "local_phone", "local_email")
        }),
        ("Lead Routing", {
            "fields": (
                "lead_notification_email", "from_email", "reply_to_email",
                "assigned_user", "assigned_salesperson",
            )
        }),
        ("Content", {
            "fields": ("intro_text", "seo_body", "zip_codes_preview")
        }),
        ("Map", {
            "fields": ("latitude", "longitude")
        }),
    )

    def related_cities(self, obj):
        cities = ServiceCity.objects.filter(sales_point=obj, is_active=True).order_by("order", "name")
        return ", ".join(city.name for city in cities) or "-"
    related_cities.short_description = "Cities"

    def related_zip_codes(self, obj):
        cities = ServiceCity.objects.filter(sales_point=obj, is_active=True).order_by("order", "name")
        parts = []
        for city in cities:
            zip_codes = city.zip_codes.order_by("code")
            codes = ", ".join(zip_code.code for zip_code in zip_codes)
            parts.append(f"{city.name}: {codes or '-'}")
        return format_html("<br>".join(parts)) if parts else "-"
    related_zip_codes.short_description = "Zip codes"

    def zip_codes_preview(self, obj):
        if not obj.pk:
            return "-"
        cities = ServiceCity.objects.filter(sales_point=obj, is_active=True).order_by("order", "name")
        lines = []
        for city in cities:
            zip_codes = city.zip_codes.order_by("code")
            codes = ", ".join(zip_code.code for zip_code in zip_codes)
            lines.append(f"{city.name}: {codes or '-'}")
        return format_html("<br>".join(lines)) if lines else "-"
    zip_codes_preview.short_description = "Related zip codes"

    def get_urls(self):
        urls = super().get_urls()
        extra = [
            path(
                "<int:pk>/manage-territory/",
                self.admin_site.admin_view(self.manage_territory_view),
                name="home_salespoint_manage_territory",
            ),
            path(
                "import-territory-csv/",
                self.admin_site.admin_view(self.import_territory_csv_view),
                name="home_salespoint_import_territory_csv",
            ),
        ]
        return extra + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["import_territory_csv_url"] = "import-territory-csv/"
        return super().changelist_view(request, extra_context=extra_context)

    def import_territory_csv_view(self, request):
        if request.method == "POST":
            csv_file = request.FILES.get("csv_file")
            if not csv_file or not csv_file.name.endswith(".csv"):
                messages.error(request, "Please upload a valid .csv file.")
                return redirect(".")

            created_cities = created_zips = assigned = 0
            errors = []

            text = io.TextIOWrapper(csv_file, encoding="utf-8-sig")
            reader = csv.DictReader(text)

            for i, row in enumerate(reader, start=2):
                try:
                    slug = row["sales_point_slug"].strip()
                    try:
                        sales_point = SalesPoint.objects.get(slug=slug)
                    except SalesPoint.DoesNotExist:
                        errors.append(
                            f"Row {i}: Sales point '{slug}' not found — create it first."
                        )
                        continue

                    city, city_created = ServiceCity.objects.get_or_create(
                        name=row["city_name"].strip(),
                        state=row["state"].strip(),
                        defaults={"is_active": True, "sales_point": sales_point},
                    )
                    if city_created:
                        created_cities += 1
                    elif city.sales_point != sales_point:
                        city.sales_point = sales_point
                        city.save(update_fields=["sales_point"])
                        assigned += 1

                    _, zip_created = ZipCode.objects.get_or_create(
                        code=row["zip_code"].strip(),
                        defaults={"service_city": city},
                    )
                    if zip_created:
                        created_zips += 1

                except Exception as e:
                    errors.append(f"Row {i}: {e}")

            for err in errors[:10]:
                messages.warning(request, err)

            messages.success(
                request,
                f"Import complete — {created_cities} new cities, "
                f"{assigned} reassigned, {created_zips} new zip codes.",
            )
            return redirect("..")

        context = {
            **self.admin_site.each_context(request),
            "title": "Import territory from CSV",
            "opts": self.model._meta,
            "sales_points": SalesPoint.objects.filter(is_active=True).order_by("name"),
        }
        return render(request, "admin/home/salespoint/import_territory_csv.html", context)

    def manage_territory_link(self, obj):
        if not obj.pk:
            return "-"
        return format_html(
            '<a href="{}/manage-territory/" class="button" '
            'style="padding:3px 10px;font-size:12px;">Manage Territory</a>',
            obj.pk,
        )
    manage_territory_link.short_description = "Territory"

    def manage_territory_view(self, request, pk):
        sales_point = SalesPoint.objects.get(pk=pk)

        def build_assigned(sp):
            cities = ServiceCity.objects.filter(sales_point=sp).order_by("state", "name")
            lines = []
            for city in cities:
                codes = ", ".join(z.code for z in city.zip_codes.order_by("code"))
                lines.append(f"{city.name}, {city.state}: {codes}")
            return "\n".join(lines)

        if request.method == "POST":
            action = request.POST.get("action")

            # ── action: assign checked cities ──────────────────────────────
            if action == "assign":
                city_ids = request.POST.getlist("city_ids")
                if city_ids:
                    assigned = ServiceCity.objects.filter(pk__in=city_ids).update(
                        sales_point=sales_point
                    )
                    messages.success(request, f"{assigned} city/cities assigned to {sales_point.name}.")
                else:
                    messages.warning(request, "No cities selected.")

            # ── action: unassign checked cities ────────────────────────────
            elif action == "unassign":
                city_ids = request.POST.getlist("assigned_city_ids")
                if city_ids:
                    removed = ServiceCity.objects.filter(
                        pk__in=city_ids, sales_point=sales_point
                    ).update(sales_point=None)
                    messages.success(request, f"{removed} city/cities removed from {sales_point.name}.")
                else:
                    messages.warning(request, "No cities selected.")

            # ── action: bulk textarea entry ─────────────────────────────────
            elif action == "textarea":
                raw = request.POST.get("territory", "")
                created_cities = created_zips = 0
                errors = []

                for lineno, line in enumerate(raw.splitlines(), start=1):
                    line = line.strip()
                    if not line:
                        continue
                    if ":" not in line:
                        errors.append(f"Line {lineno}: missing colon — expected 'City, State: zip1 zip2 …'")
                        continue
                    city_part, zip_part = line.split(":", 1)
                    city_part = city_part.strip()
                    zip_part = zip_part.strip()

                    if "," not in city_part:
                        errors.append(f"Line {lineno}: missing comma — expected 'City, State'")
                        continue
                    city_name, state = [p.strip() for p in city_part.rsplit(",", 1)]

                    city, city_created = ServiceCity.objects.get_or_create(
                        name=city_name,
                        state=state,
                        defaults={"is_active": True, "sales_point": sales_point},
                    )
                    if city_created:
                        created_cities += 1
                    elif city.sales_point != sales_point:
                        city.sales_point = sales_point
                        city.save(update_fields=["sales_point"])

                    zip_codes = [z.strip() for z in re.split(r"[\s,]+", zip_part) if z.strip()]
                    for code in zip_codes:
                        _, zip_created = ZipCode.objects.get_or_create(
                            code=code, defaults={"service_city": city}
                        )
                        if zip_created:
                            created_zips += 1

                for err in errors[:10]:
                    messages.warning(request, err)
                if created_cities or created_zips:
                    messages.success(
                        request,
                        f"Saved — {created_cities} new cities, {created_zips} new zip codes added.",
                    )
                elif not errors:
                    messages.info(request, "No new data — everything already exists.")

        # ── build context ───────────────────────────────────────────────────
        q = request.GET.get("q", "").strip()

        assigned_cities = ServiceCity.objects.filter(
            sales_point=sales_point
        ).order_by("state", "name")

        available_qs = ServiceCity.objects.exclude(
            sales_point=sales_point
        ).order_by("state", "name")
        if q:
            available_qs = available_qs.filter(
                models.Q(name__icontains=q) | models.Q(state__icontains=q)
            )

        # group available cities by state for easier reading
        from itertools import groupby
        available_by_state = [
            (state, list(group))
            for state, group in groupby(available_qs, key=lambda c: c.state)
        ]

        context = {
            **self.admin_site.each_context(request),
            "title": f"Manage Territory — {sales_point.name}",
            "opts": self.model._meta,
            "sales_point": sales_point,
            "assigned_cities": assigned_cities,
            "available_by_state": available_by_state,
            "q": q,
        }
        return render(request, "admin/home/salespoint/manage_territory.html", context)


# ── FranchiseAgreement ────────────────────────────────────────────────────

@admin.register(FranchiseAgreement)
class FranchiseAgreementAdmin(admin.ModelAdmin):
    list_display = (
        "sales_point", "franchisee_legal_name", "status",
        "royalty_rate", "agreement_date", "expiry_date",
    )
    list_filter = ("status",)
    search_fields = (
        "sales_point__name", "franchisee_legal_name",
        "franchisee_email", "franchisee_contact_name",
    )
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Location", {"fields": ("sales_point",)}),
        ("Franchisee", {
            "fields": (
                "franchisee_legal_name", "franchisee_contact_name",
                "franchisee_email", "franchisee_phone",
            )
        }),
        ("Financial terms", {
            "fields": ("upfront_fee", "royalty_rate", "marketing_fee_rate")
        }),
        ("Agreement lifecycle", {
            "fields": (
                "status", "agreement_date", "start_date",
                "expiry_date", "renewal_date",
            )
        }),
        ("Territory & documents", {
            "fields": ("territory_notes", "agreement_document")
        }),
        ("Notes & audit", {
            "fields": ("internal_notes", "created_at", "updated_at")
        }),
    )


# ── Gallery ───────────────────────────────────────────────────────────────

@admin.register(Gallery)
class GalleryAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "order", "created_at")
    list_filter = ("is_active", "sales_points")
    search_fields = ("name", "page_title", "intro_text")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("order", "name")
    inlines = [GalleryItemInline]
    fields = (
        "name", "slug", "sales_points", "thumbnail",
        "page_title", "intro_text", "is_active", "order",
    )
    filter_horizontal = ("sales_points",)


# ── Testimonial ───────────────────────────────────────────────────────────

@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ("order", "name", "rating", "is_active", "is_featured")
    list_filter = ("is_active", "is_featured", "rating")
    search_fields = ("name", "message")
    ordering = ("order",)


# ── LeadActivity (standalone admin) ───────────────────────────────────────

@admin.register(LeadActivity)
class LeadActivityAdmin(admin.ModelAdmin):
    list_display = ("created_at", "lead_link", "action", "user", "detail_short")
    list_filter = ("action", "created_at")
    search_fields = ("lead__first_name", "lead__last_name", "detail", "user__email")
    readonly_fields = ("created_at", "lead", "user", "action", "detail")
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def lead_link(self, obj):
        return format_html(
            '<a href="/admin/home/leadmodel/{}/change/">Lead #{}</a>',
            obj.lead_id, obj.lead_id,
        )
    lead_link.short_description = "Lead"

    def detail_short(self, obj):
        return obj.detail[:80] + "…" if len(obj.detail) > 80 else obj.detail
    detail_short.short_description = "Detail"


# ── LeadModel ─────────────────────────────────────────────────────────────

class StaleLeadFilter(admin.SimpleListFilter):
    title = "Stale leads"
    parameter_name = "stale"

    def lookups(self, request, model_admin):
        return [
            ("24h", "New — over 24 hours old"),
            ("48h", "New — over 48 hours old"),
            ("7d", "New — over 7 days old"),
        ]

    def queryset(self, request, queryset):
        cutoffs = {"24h": 1, "48h": 2, "7d": 7}
        days = cutoffs.get(self.value())
        if days:
            threshold = now() - timedelta(days=days)
            return queryset.filter(status="new", created_at__lte=threshold)
        return queryset


@admin.register(LeadModel)
class LeadModelAdmin(admin.ModelAdmin):
    list_display = (
        "id", "first_name", "last_name", "email", "phone", "zip_code",
        "service_city", "sales_point", "assigned_user",
        "status", "created_at",
    )
    list_filter = ("sales_point", "service_city", "status", StaleLeadFilter, "created_at")
    list_editable = ("status",)
    search_fields = (
        "first_name", "last_name", "email", "phone", "zip_code",
        "message", "source_page",
    )
    readonly_fields = ("created_at",)
    inlines = [LeadAttachmentInline, LeadActivityInline]
    ordering = ("-created_at",)
    save_on_top = True


# ── VideoReview ───────────────────────────────────────────────────────────

@admin.register(VideoReview)
class VideoReviewAdmin(admin.ModelAdmin):
    list_display = ("order", "title", "customer_name", "is_active", "is_featured", "created_at")
    list_filter = ("is_active", "is_featured")
    search_fields = ("title", "customer_name")
    ordering = ("order", "-created_at")