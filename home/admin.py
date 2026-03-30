from django.contrib import admin
from .models import Gallery, GalleryItem, Testimonial, LeadModel, LeadAttachment, VideoReview


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
    list_filter = ("is_active",)
    search_fields = ("name", "page_title", "intro_text")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("order", "name")
    inlines = [GalleryItemInline]
    fields = (
        "name",
        "slug",
        "thumbnail",
        "page_title",
        "intro_text",
        "is_active",
        "order",
    )


@admin.register(GalleryItem)
class GalleryItemAdmin(admin.ModelAdmin):
    list_display = ("gallery", "media_type", "title", "sort_order", "created_at")
    list_filter = ("gallery", "media_type")
    search_fields = ("title", "section_heading", "text_before", "text_after")
    ordering = ("gallery", "sort_order", "id")


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
    list_display = ("id", "name", "email", "phone", "created_at")
    search_fields = ("name", "email", "phone", "message")
    readonly_fields = ("created_at",)
    inlines = [LeadAttachmentInline]
    ordering = ("-created_at",)


@admin.register(VideoReview)
class VideoReviewAdmin(admin.ModelAdmin):
    list_display = ("order", "title", "customer_name", "is_active", "is_featured", "created_at")
    list_filter = ("is_active", "is_featured")
    search_fields = ("title", "customer_name")
    ordering = ("order", "-created_at")