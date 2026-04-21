from django.urls import path
from . import views

app_name = "panel"

urlpatterns = [
    # Dashboard
    path("", views.dashboard, name="dashboard"),

    # Projects
    path("projects/", views.project_list, name="project_list"),
    path("projects/new/", views.project_create, name="project_create"),
    path("projects/<int:pk>/", views.project_detail, name="project_detail"),
    path("projects/<int:pk>/edit/", views.project_edit, name="project_edit"),
    path("projects/<int:pk>/delete/", views.project_delete, name="project_delete"),

    # Customers
    path("customers/", views.customer_list, name="customer_list"),
    path("customers/new/", views.customer_create, name="customer_create"),
    path("customers/<int:pk>/", views.customer_detail, name="customer_detail"),
    path("customers/<int:pk>/edit/", views.customer_edit, name="customer_edit"),
    path("customers/<int:pk>/delete/", views.customer_delete, name="customer_delete"),

    # Estimates
    path("estimates/", views.estimate_list, name="estimate_list"),
    path("estimates/new/", views.estimate_create, name="estimate_create"),
    path("estimates/<int:pk>/", views.estimate_detail, name="estimate_detail"),
    path("estimates/<int:pk>/edit/", views.estimate_edit, name="estimate_edit"),
    path("estimates/<int:pk>/ajax/search-parts/", views.ajax_estimate_search_parts, name="ajax_estimate_search_parts"),
    path("estimates/<int:pk>/ajax/add-item/", views.ajax_estimate_add_item, name="ajax_estimate_add_item"),
    path("estimates/<int:pk>/ajax/update-item/<int:item_pk>/", views.ajax_estimate_update_item, name="ajax_estimate_update_item"),
    path("estimates/<int:pk>/ajax/delete-item/<int:item_pk>/", views.ajax_estimate_delete_item, name="ajax_estimate_delete_item"),
    path("estimates/<int:pk>/ajax/update-header/", views.ajax_estimate_update_header, name="ajax_estimate_update_header"),

    # Invoices
    path("invoices/", views.invoice_list, name="invoice_list"),
    path("invoices/new/", views.invoice_create, name="invoice_create"),
    path("invoices/<int:pk>/", views.invoice_detail, name="invoice_detail"),

    # Transactions
    path("transactions/", views.transaction_list, name="transaction_list"),
    path("transactions/new/", views.transaction_create, name="transaction_create"),

    # Parts
    path("parts/", views.part_list, name="part_list"),
    path("parts/<int:pk>/edit/", views.part_edit, name="part_edit"),
    path("parts/ajax/delete/", views.ajax_parts_delete, name="ajax_parts_delete"),
    path("parts/ajax/global-list/", views.ajax_global_parts_list, name="ajax_global_parts_list"),
    path("parts/ajax/add-global/", views.ajax_parts_add_global, name="ajax_parts_add_global"),
    path("parts/ajax/update-price/", views.ajax_parts_update_price, name="ajax_parts_update_price"),
    path("parts/ajax/detail/", views.ajax_part_detail, name="ajax_part_detail"),
    path("parts/ajax/list/", views.ajax_parts_list, name="ajax_parts_list"),
    path("parts/ajax/create/", views.ajax_parts_create, name="ajax_parts_create"),
    path("parts/ajax/units/", views.ajax_units, name="ajax_units"),
    path("parts/ajax/category/add/", views.ajax_category_add, name="ajax_category_add"),
    path("parts/ajax/category/add-global/", views.ajax_category_add_global, name="ajax_category_add_global"),
    path("parts/ajax/category/remove/", views.ajax_category_remove, name="ajax_category_remove"),
    path("parts/ajax/unit/add/", views.ajax_unit_add, name="ajax_unit_add"),
    path("parts/ajax/unit/add-global/", views.ajax_unit_add_global, name="ajax_unit_add_global"),
    path("parts/ajax/unit/remove/", views.ajax_unit_remove, name="ajax_unit_remove"),

    # Tasks
    path("tasks/", views.task_list, name="task_list"),
    path("tasks/list/new/", views.task_list_create, name="task_list_create"),
    path("tasks/list/<int:list_pk>/new/", views.task_create, name="task_create"),
    path("tasks/<int:pk>/toggle/", views.task_toggle, name="task_toggle"),

    # Leads
    path("leads/", views.lead_list, name="lead_list"),
    path("leads/new/", views.lead_create, name="lead_create"),
    path("leads/<int:pk>/", views.lead_detail, name="lead_detail"),

    # Lead → Customer + Estimate
    path("lead/<int:lead_pk>/to-estimate/", views.lead_to_estimate, name="lead_to_estimate"),
]
