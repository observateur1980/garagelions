from django.contrib import admin
from .models import (
    Customer, Project, PartCategory, SalesPointPartCategory,
    Unit, SalesPointUnit, SalesPointPart, Part,
    Estimate, EstimateItem, Invoice, InvoiceItem,
    Transaction, TaskList, Task,
)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "phone", "city", "created_at")
    search_fields = ("first_name", "last_name", "email", "phone")


class EstimateItemInline(admin.TabularInline):
    model = EstimateItem
    extra = 0


@admin.register(Estimate)
class EstimateAdmin(admin.ModelAdmin):
    list_display = ("estimate_number", "title", "customer", "total", "status", "created_at")
    list_filter = ("status",)
    inlines = [EstimateItemInline]


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "title", "customer", "total", "amount_paid", "status")
    list_filter = ("status",)
    inlines = [InvoiceItemInline]


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "customer", "status", "created_at")
    list_filter = ("status",)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("date", "transaction_type", "amount", "customer", "invoice")
    list_filter = ("transaction_type",)


@admin.register(SalesPointPart)
class SalesPointPartAdmin(admin.ModelAdmin):
    list_display = ("sales_point", "part")


@admin.register(Part)
class PartAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "category", "sales_point", "is_active")
    list_filter = ("category", "is_active", "sales_point")


class PartInline(admin.TabularInline):
    model = Part
    extra = 1
    fields = ("name", "sku", "unit", "unit_price", "is_active")
    show_change_link = True


@admin.register(PartCategory)
class PartCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "sales_point", "is_active")
    list_filter = ("is_active", "sales_point")
    inlines = [PartInline]


@admin.register(SalesPointPartCategory)
class SalesPointPartCategoryAdmin(admin.ModelAdmin):
    list_display = ("sales_point", "category")


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ("name", "abbreviation", "sales_point", "is_active")
    list_filter = ("is_active", "sales_point")


@admin.register(SalesPointUnit)
class SalesPointUnitAdmin(admin.ModelAdmin):
    list_display = ("sales_point", "unit")


class TaskInline(admin.TabularInline):
    model = Task
    extra = 0


@admin.register(TaskList)
class TaskListAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "created_by")
    inlines = [TaskInline]


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "task_list", "is_completed", "is_starred", "due_date")
    list_filter = ("is_completed", "is_starred")
