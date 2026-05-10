# home/admin.py — COMPLETE FILE (replace your existing one)

import csv
import io
import os
import re

from django import forms
from django.conf import settings
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
    LeadStatus,
    LeadActivity,
    LeadAttachment,
    VideoReview,
    ServiceCity,
    FranchiseAgreement,
    State,
    Region,
    ZipCoverage,
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


# ── Territory: State / Region / ZipCoverage ──────────────────────────────

class StateRegionInline(admin.TabularInline):
    model = Region
    fk_name = "state"
    extra = 0
    can_delete = False
    show_change_link = True
    verbose_name = "Region in this state"
    verbose_name_plural = "Regions in this state"
    fields = ("code", "name", "internal_label", "is_active")
    readonly_fields = fields
    ordering = ("code",)

    def has_add_permission(self, request, obj=None):
        return False


class StateZipCoverageInline(admin.TabularInline):
    model = ZipCoverage
    fk_name = "state"
    extra = 0
    can_delete = False
    show_change_link = True
    verbose_name = "ZIP in this state"
    verbose_name_plural = "ZIPs in this state"
    fields = ("zip_code", "city", "region", "sales_point", "backup_sales_point", "coverage_type", "is_active")
    readonly_fields = fields
    ordering = ("region__code", "zip_code")

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "region", "sales_point", "backup_sales_point",
        )


@admin.register(State)
class StateAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "region_count", "sales_point_count", "zip_coverage_count", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")
    ordering = ("code",)
    inlines = [StateRegionInline, StateZipCoverageInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _region_count=models.Count("regions", distinct=True),
            _sp_count=models.Count("regions__sales_points", distinct=True),
            _zc_count=models.Count("zip_coverages", distinct=True),
        )

    def region_count(self, obj):
        return obj._region_count
    region_count.short_description = "# Regions"
    region_count.admin_order_field = "_region_count"

    def sales_point_count(self, obj):
        return obj._sp_count
    sales_point_count.short_description = "# SPs"
    sales_point_count.admin_order_field = "_sp_count"

    def zip_coverage_count(self, obj):
        return obj._zc_count
    zip_coverage_count.short_description = "# ZIPs"
    zip_coverage_count.admin_order_field = "_zc_count"


class RegionSalesPointInline(admin.TabularInline):
    model = SalesPoint
    fk_name = "region"
    extra = 0
    can_delete = False
    show_change_link = True
    verbose_name = "Sales point in this region"
    verbose_name_plural = "Sales points in this region"
    fields = ("name", "code", "base_city", "location_type", "is_active")
    readonly_fields = fields
    ordering = ("order", "name")

    def has_add_permission(self, request, obj=None):
        return False


class RegionZipCoverageInline(admin.TabularInline):
    model = ZipCoverage
    fk_name = "region"
    extra = 0
    can_delete = False
    show_change_link = True
    verbose_name = "ZIP in this region"
    verbose_name_plural = "ZIPs in this region"
    fields = ("zip_code", "city", "sales_point", "backup_sales_point", "coverage_type", "is_active")
    readonly_fields = fields
    ordering = ("zip_code",)

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("sales_point", "backup_sales_point")


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("internal_code", "name", "state", "sales_point_count", "zip_coverage_count", "is_active")
    list_filter = ("state", "is_active")
    search_fields = ("code", "name", "state__code", "state__name")
    autocomplete_fields = ("state",)
    ordering = ("state__code", "code")
    inlines = [RegionSalesPointInline, RegionZipCoverageInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _sp_count=models.Count("sales_points", distinct=True),
            _zc_count=models.Count("zip_coverages", distinct=True),
        )

    def internal_code(self, obj):
        return obj.internal_code
    internal_code.short_description = "Code"
    internal_code.admin_order_field = "code"

    def sales_point_count(self, obj):
        return obj._sp_count
    sales_point_count.short_description = "# SPs"
    sales_point_count.admin_order_field = "_sp_count"

    def zip_coverage_count(self, obj):
        return obj._zc_count
    zip_coverage_count.short_description = "# ZIPs"
    zip_coverage_count.admin_order_field = "_zc_count"


@admin.register(ZipCoverage)
class ZipCoverageAdmin(admin.ModelAdmin):
    list_display = (
        "zip_code", "city", "county", "state", "region",
        "sales_point", "backup_sales_point", "coverage_type",
        "drive_time_target", "is_active",
    )
    list_filter = ("state", "region", "coverage_type", "is_active", "sales_point")
    search_fields = ("zip_code", "city", "county")
    autocomplete_fields = ("state", "region", "sales_point", "backup_sales_point")
    ordering = ("state__code", "region__code", "zip_code")
    list_editable = ("coverage_type", "is_active")


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
        "name", "internal_code_display", "state_code", "region_code",
        "location_type", "base_city",
        "primary_zip_count", "backup_zip_count", "city_count",
        "local_phone", "assigned_user",
        "is_active", "is_featured", "order",
        "manage_territory_link",
    )
    list_display_links = ("name", "internal_code_display")
    list_editable = ("is_active", "is_featured", "order")
    list_filter = (
        "region__state", "region", "location_type",
        "is_active", "is_featured",
    )
    search_fields = (
        "name", "code", "base_city", "local_email", "lead_notification_email",
        "region__code", "region__name", "region__state__code", "region__state__name",
    )
    autocomplete_fields = ("region",)
    prepopulated_fields = {"slug": ("name",)}
    inlines = [SalesPointWorkingHourInline, FranchiseAgreementInline]
    readonly_fields = ("zip_codes_preview", "internal_code")

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("region", "region__state", "assigned_user")
        return qs.annotate(
            _primary_zip_count=models.Count("primary_zip_coverages", distinct=True),
            _backup_zip_count=models.Count("backup_zip_coverages", distinct=True),
            _city_count=models.Count("cities", distinct=True),
        )

    def internal_code_display(self, obj):
        return obj.internal_code or "—"
    internal_code_display.short_description = "Code"
    internal_code_display.admin_order_field = "code"

    def state_code(self, obj):
        return obj.region.state.code if obj.region_id else "—"
    state_code.short_description = "State"
    state_code.admin_order_field = "region__state__code"

    def region_code(self, obj):
        return obj.region.code if obj.region_id else "—"
    region_code.short_description = "Region"
    region_code.admin_order_field = "region__code"

    def primary_zip_count(self, obj):
        return obj._primary_zip_count
    primary_zip_count.short_description = "# ZIPs"
    primary_zip_count.admin_order_field = "_primary_zip_count"

    def backup_zip_count(self, obj):
        return obj._backup_zip_count
    backup_zip_count.short_description = "# Backup"
    backup_zip_count.admin_order_field = "_backup_zip_count"

    def city_count(self, obj):
        return obj._city_count
    city_count.short_description = "# Cities"
    city_count.admin_order_field = "_city_count"

    fieldsets = (
        ("Basic", {
            "fields": (
                "name", "slug", "location_type", "royalty_rate",
                "is_active", "is_featured", "order",
            )
        }),
        ("Territory", {
            "fields": ("region", "code", "base_city", "internal_code"),
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
        "name", "slug", "sales_points", "thumbnail", "thumbnail_mobile",
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


def _lead_status_choices(current_code=None):
    """LeadStatus.code/label pairs, plus the row's current code as a fallback.

    Mirrors home.forms._db_status_choices. Without the fallback, a row whose
    status was removed from the LeadStatus table (or that simply isn't a
    seeded choice) renders a <select> with no matching <option>; the browser
    then visually shows the first option, and saving silently rewrites the
    DB to that value.
    """
    choices = list(LeadStatus.objects.values_list("code", "label"))
    if current_code and not any(c == current_code for c, _ in choices):
        choices.append((current_code, current_code.replace("_", " ").title()))
    return choices


class LeadAdminChangelistForm(forms.ModelForm):
    """Form used per-row on the changelist when list_editable is active.

    Populates the status dropdown from LeadStatus so custom codes
    (e.g. "in_operation", "disqualified") survive a save sweep.
    """

    class Meta:
        model = LeadModel
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "status" in self.fields:
            current = self.instance.status if self.instance and self.instance.pk else None
            self.fields["status"].choices = _lead_status_choices(current_code=current)


class LeadAdminChangeForm(LeadAdminChangelistForm):
    """Form used on the single-lead change page. Same dynamic-choices fix."""
    pass


@admin.register(LeadModel)
class LeadModelAdmin(admin.ModelAdmin):
    form = LeadAdminChangeForm
    list_display = (
        "id", "first_name", "last_name", "email", "phone", "zip_code",
        "service_city", "sales_point", "assigned_user",
        "status",
    )
    list_editable = ("status",)
    search_fields = (
        "first_name", "last_name", "email", "phone", "zip_code",
        "message", "source_page",
    )
    readonly_fields = ("created_at",)
    inlines = [LeadAttachmentInline, LeadActivityInline]
    ordering = ("-created_at",)
    save_on_top = True

    def get_changelist_form(self, request, **kwargs):
        return LeadAdminChangelistForm

    class Media:
        css = {"all": ("css/admin_lead.css",)}
        js = ("js/admin_lead_status.js",)


# ── VideoReview ───────────────────────────────────────────────────────────

VIDEO_EXTS = {".mp4", ".mov", ".webm", ".m4v", ".avi", ".mkv"}


def _scan_video_review_files():
    """Return list of (relative_path, label) for video files in media/video_reviews/.

    Sorted by mtime descending so the most recently SFTP'd file is at the top.
    """
    target_dir = os.path.join(settings.MEDIA_ROOT, "video_reviews")
    if not os.path.isdir(target_dir):
        return []
    entries = []
    for name in os.listdir(target_dir):
        full = os.path.join(target_dir, name)
        if not os.path.isfile(full):
            continue
        if os.path.splitext(name)[1].lower() not in VIDEO_EXTS:
            continue
        size_mb = os.path.getsize(full) / (1024 * 1024)
        entries.append((os.path.getmtime(full), f"video_reviews/{name}", f"{name} ({size_mb:.1f} MB)"))
    entries.sort(key=lambda x: x[0], reverse=True)
    return [(rel, label) for _, rel, label in entries]


class VideoReviewAdminForm(forms.ModelForm):
    existing_video = forms.ChoiceField(
        required=False,
        label="Or pick existing file from server",
        help_text="Drop large files into media/video_reviews/ via SFTP and select them here. "
                  "Bypasses the browser upload entirely.",
    )

    class Meta:
        model = VideoReview
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Either the upload field OR the picker can satisfy the requirement
        self.fields["video"].required = False
        choices = [("", "— Use upload field above —")] + _scan_video_review_files()
        self.fields["existing_video"].choices = choices

    def clean(self):
        cleaned = super().clean()
        existing = cleaned.get("existing_video")
        uploaded = cleaned.get("video")
        if not self.instance.pk and not uploaded and not existing:
            raise forms.ValidationError(
                "Upload a video or pick an existing file from the server."
            )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        existing = self.cleaned_data.get("existing_video")
        if existing:
            # Point the FileField at the file already on disk; no copy/upload happens.
            instance.video.name = existing
        if commit:
            instance.save()
            self.save_m2m()
        return instance


@admin.register(VideoReview)
class VideoReviewAdmin(admin.ModelAdmin):
    form = VideoReviewAdminForm
    list_display = ("order", "title", "customer_name", "is_active", "is_featured", "created_at")
    list_filter = ("is_active", "is_featured")
    search_fields = ("title", "customer_name")
    ordering = ("order", "-created_at")
    fields = (
        "title",
        "customer_name",
        "video",
        "existing_video",
        "thumbnail",
        "is_active",
        "is_featured",
        "order",
    )

    class Media:
        css = {"all": ("css/admin_video_review_upload.css",)}
        js = ("js/admin_video_review_upload.js",)