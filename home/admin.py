from django.contrib import admin
from django.utils.html import format_html
from .models import (
    SalesPoint,
    SalesPointWorkingHour,
    ZipCode,
    Gallery,
    GalleryItem,
    Testimonial,
    LeadModel,
    LeadAttachment,
    VideoReview,
    ServiceCity,

)


class ZipCodeInline(admin.TabularInline):
    model = ZipCode
    extra = 1


class SalesPointWorkingHourInline(admin.TabularInline):
    model = SalesPointWorkingHour
    extra = 0
    fields = ("day", "is_open", "open_time", "close_time", "note")

@admin.register(ServiceCity)
class ServiceCityAdmin(admin.ModelAdmin):
    list_display = ("name", "state", "sales_point", "is_active", "order")
    list_filter = ("sales_point", "state", "is_active")
    search_fields = ("name", "state", "sales_point__name")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ZipCodeInline]


@admin.register(ZipCode)
class ZipCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "service_city", "sales_point_name")
    search_fields = ("code", "service_city__name", "service_city__sales_point__name")

    def sales_point_name(self, obj):
        return obj.service_city.sales_point.name



class CityInline(admin.TabularInline):
    model = ServiceCity
    extra = 1

@admin.register(SalesPoint)
class SalesPointAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "local_phone",
        "local_email",
        "assigned_user",
        "is_active",
        "is_featured",
        "order",
        "related_cities",
        "related_zip_codes",
    )
    list_editable = ("is_active", "is_featured", "order")
    search_fields = ("name", "local_email", "lead_notification_email")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [SalesPointWorkingHourInline, CityInline]
    readonly_fields = ("zip_codes_preview",)

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
            if codes:
                parts.append(f"{city.name}: {codes}")
            else:
                parts.append(f"{city.name}: -")

        if not parts:
            return "-"

        return format_html("<br>".join(parts))
    related_zip_codes.short_description = "Zip codes"

    def zip_codes_preview(self, obj):
        if not obj.pk:
            return "-"

        cities = ServiceCity.objects.filter(sales_point=obj).order_by("order", "name")
        lines = []

        for city in cities:
            zip_codes = city.zip_codes.order_by("code")
            codes = ", ".join(zip_code.code for zip_code in zip_codes)
            if codes:
                lines.append(f"{city.name}: {codes}")
            else:
                lines.append(f"{city.name}: -")

        if not lines:
            return "-"

        return format_html("<br>".join(lines))
    zip_codes_preview.short_description = "Related zip codes"

    fieldsets = (
        ("Basic", {
            "fields": ("name", "slug", "is_active", "is_featured", "order")
        }),
        ("SEO", {
            "fields": ("page_title", "meta_description", "hero_title", "hero_subtitle")
        }),
        ("Address", {
            "fields": ("address_line_1", "address_line_2", "local_phone", "local_email")
        }),
        ("Lead Routing", {
            "fields": ("lead_notification_email", "from_email", "reply_to_email", "assigned_user", "assigned_salesperson")
        }),
        ("Content", {
            "fields": ("intro_text", "seo_body", "zip_codes_preview")
        }),
        ("Map", {
            "fields": ("latitude", "longitude")
        }),
    )




class GalleryItemInline(admin.StackedInline):
    model = GalleryItem
    extra = 1
    fields = (
        "sort_order",
        "media_type",
        "file",
        "thumbnail",
        "title",
        "section_heading",
        "text_before",
        "text_after",
    )


@admin.register(Gallery)
class GalleryAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "order", "created_at")
    list_filter = ("is_active", "sales_points")
    search_fields = ("name", "page_title", "intro_text")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("order", "name")
    inlines = [GalleryItemInline]
    fields = (
        "name",
        "slug",
        "sales_points",
        "thumbnail",
        "page_title",
        "intro_text",
        "is_active",
        "order",
    )
    filter_horizontal = ("sales_points",)


@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ("order", "name", "rating", "is_active", "is_featured")
    list_filter = ("is_active", "is_featured", "rating")
    search_fields = ("name", "message")
    ordering = ("order",)


class LeadAttachmentInline(admin.TabularInline):
    model = LeadAttachment
    extra = 0
    readonly_fields = ("uploaded_at",)


@admin.register(LeadModel)
class LeadModelAdmin(admin.ModelAdmin):
    list_display = (
        "id", "first_name", "last_name", "email", "phone", "zip_code",
        "service_city", "sales_point", "assigned_user",
        "status", "created_at"
    )
    list_filter = ("sales_point", "service_city", "status", "created_at")
    search_fields = (
        "first_name", "last_name", "email", "phone", "zip_code",
        "assigned_to", "message", "source_page"
    )
    readonly_fields = ("created_at",)
    inlines = [LeadAttachmentInline]
    ordering = ("-created_at",)


@admin.register(VideoReview)
class VideoReviewAdmin(admin.ModelAdmin):
    list_display = ("order", "title", "customer_name", "is_active", "is_featured", "created_at")
    list_filter = ("is_active", "is_featured")
    search_fields = ("title", "customer_name")
    ordering = ("order", "-created_at")