from django.contrib import admin
from .models import TaskCategory, TaskItem


@admin.register(TaskCategory)
class TaskCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "order", "created_at")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("order", "name")


@admin.register(TaskItem)
class TaskItemAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "priority", "done", "created_by", "created_at")
    list_filter = ("category", "priority", "done")
    search_fields = ("title",)
