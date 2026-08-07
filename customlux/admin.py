from django.contrib import admin

from .models import CabinetActivity, CabinetMember, CabinetProject, CabinetStage


@admin.register(CabinetStage)
class CabinetStageAdmin(admin.ModelAdmin):
    list_display = ("label", "code", "order", "is_active", "is_won", "is_lost")
    list_editable = ("order", "is_active")
    prepopulated_fields = {"code": ("label",)}


@admin.register(CabinetProject)
class CabinetProjectAdmin(admin.ModelAdmin):
    list_display = ("title", "customer_name", "stage", "quoted_amount",
                    "install_date", "archived", "created_at")
    list_filter = ("stage", "archived")
    search_fields = ("title", "customer_name", "email", "phone", "address")
    raw_id_fields = ("lead",)


@admin.register(CabinetMember)
class CabinetMemberAdmin(admin.ModelAdmin):
    list_display = ("email", "user", "can_edit", "is_active", "created_at")
    list_filter = ("can_edit", "is_active")
    search_fields = ("email",)


@admin.register(CabinetActivity)
class CabinetActivityAdmin(admin.ModelAdmin):
    list_display = ("project", "detail", "user", "created_at")
    search_fields = ("detail",)
