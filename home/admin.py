# home/admin.py — COMPLETE FILE (replace your existing one)

import csv
import io

from django.contrib import admin, messages
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


class CityInline(admin.TabularInline):
    model = ServiceCity
    extra = 1
    fields = ("name", "state", "is_active", "order")


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
    list_display = ("name", "state", "sales_point", "is_active", "order")
    list_filter = ("sales_point", "state", "is_active")
    search_fields = ("name", "state", "sales_point__name")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ZipCodeInline]


# ── ZipCode ───────────────────────────────────────────────────────────────

@admin.register(ZipCode)
class ZipCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "service_city", "sales_point_name")
    search_fields = ("code", "service_city__name", "service_city__sales_point__name")

    def sales_point_name(self, obj):
        return obj.service_city.sales_point.name
    sales_point_name.short_description = "Sales Point"


# ── SalesPoint ────────────────────────────────────────────────────────────

@admin.register(SalesPoint)
class SalesPointAdmin(admin.ModelAdmin):
    list_display = (
        "name", "location_type", "local_phone", "local_email",
        "assigned_user", "is_active", "is_featured", "order",
        "related_cities", "related_zip_codes",
    )
    list_editable = ("is_active", "is_featured", "order")
    list_filter = ("location_type", "is_active", "is_featured")
    search_fields = ("name", "local_email", "lead_notification_email")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [SalesPointWorkingHourInline, CityInline, FranchiseAgreementInline]
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
        cities = ServiceCity.objects.filter(sales_point=obj).order_by("order", "name")
        return ", ".join(city.name for city in cities) or "-"
    related_cities.short_description = "Cities"

    def related_zip_codes(self, obj):
        cities = ServiceCity.objects.filter(sales_point=obj).order_by("order", "name")
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
        cities = ServiceCity.objects.filter(sales_point=obj).order_by("order", "name")
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
                "import-csv/",
                self.admin_site.admin_view(self.import_csv_view),
                name="home_salespoint_import_csv",
            ),
        ]
        return extra + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["import_csv_url"] = "import-csv/"
        return super().changelist_view(request, extra_context=extra_context)

    def import_csv_view(self, request):
        if request.method == "POST":
            csv_file = request.FILES.get("csv_file")
            if not csv_file or not csv_file.name.endswith(".csv"):
                messages.error(request, "Please upload a valid .csv file.")
                return redirect(".")

            created_sp = created_cities = created_zips = 0
            errors = []

            text = io.TextIOWrapper(csv_file, encoding="utf-8-sig")
            reader = csv.DictReader(text)

            for i, row in enumerate(reader, start=2):
                try:
                    sales_point, sp_created = SalesPoint.objects.get_or_create(
                        slug=row["sales_point_slug"].strip(),
                        defaults={"name": row["sales_point_name"].strip(), "is_active": True},
                    )
                    if sp_created:
                        created_sp += 1

                    city, city_created = ServiceCity.objects.get_or_create(
                        sales_point=sales_point,
                        slug=row["city_slug"].strip(),
                        defaults={
                            "name": row["city_name"].strip(),
                            "state": row["state"].strip(),
                            "is_active": True,
                        },
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
                f"Import complete — SalesPoints: {created_sp}, Cities: {created_cities}, ZIPs: {created_zips}",
            )
            return redirect("..")

        context = {
            **self.admin_site.each_context(request),
            "title": "Import ZIP codes from CSV",
            "opts": self.model._meta,
        }
        return render(request, "admin/home/salespoint/import_csv.html", context)


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