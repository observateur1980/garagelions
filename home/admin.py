# admin.py
# home/admin.py
from django.contrib import admin
from .models import VideoReview
from .models import LeadModel, LeadAttachment
from django.utils.html import format_html
from .models import (
    Project,
    ProjectBeforeImage,
    ProjectConstructionImage,
    ProjectAfterImage,
    ProjectTag,
    Testimonial
)




@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ("order", "name", "rating", "is_featured", "is_active")
    list_display_links = ("name",)
    list_editable = ("order", "is_featured")
    list_filter = ("is_featured", "is_active", "rating")
    search_fields = ("name", "message")
    ordering = ("order",)


class ImageInline(admin.TabularInline):
    extra = 1
    fields = ("preview", "image", "caption", "sort_order")
    readonly_fields = ("preview",)

    def preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height:60px;border-radius:6px;" />',
                obj.image.url
            )
        return "-"


class BeforeInline(ImageInline):
    model = ProjectBeforeImage


class ConstructionInline(ImageInline):
    model = ProjectConstructionImage


class AfterInline(ImageInline):
    model = ProjectAfterImage


@admin.register(ProjectTag)
class ProjectTagAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("project_name", "cover_preview", "created_at", "order")
    list_editable = ("order",)  # 👈 edit order inline
    ordering = ("order",)
    search_fields = ("project_name",)
    prepopulated_fields = {"slug": ("project_name",)}
    inlines = [BeforeInline, ConstructionInline, AfterInline]
    filter_horizontal = ("tags",)

    def cover_preview(self, obj):
        if obj.cover_image:
            return format_html(
                '<img src="{}" style="height:45px;border-radius:6px;" />',
                obj.cover_image.url
            )
        return "-"


class LeadAttachmentInline(admin.TabularInline):
    model = LeadAttachment
    extra = 0
    fields = ("file", "uploaded_at")
    readonly_fields = ("uploaded_at",)

@admin.register(LeadModel)
class LeadAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'email', 'phone', 'get_consultation_types_display', 'created_at')
    list_filter = ('consultation_types', 'created_at')
    search_fields = ('name', 'email', 'phone')

    list_display_links = ('name',)
    inlines = [LeadAttachmentInline]




@admin.register(VideoReview)
class VideoReviewAdmin(admin.ModelAdmin):
    list_display = ("order", "title", "customer_name", "is_active", "is_featured", "created_at")
    list_display_links = ("title",)   # ✅ make title the clickable link
    list_editable = ("order", "is_active", "is_featured")
    search_fields = ("title", "customer_name")
    list_filter = ("is_active", "is_featured")
    ordering = ("order", "-created_at")
