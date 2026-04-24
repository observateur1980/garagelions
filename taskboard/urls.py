from django.urls import path
from . import views

app_name = "taskboard"

urlpatterns = [
    path("", views.board, name="board"),
    path("api/tasks/", views.api_tasks, name="api_tasks"),
    path("api/tasks/<int:pk>/", views.api_task_detail, name="api_task_detail"),
    path("api/tasks/<int:pk>/toggle/", views.api_task_toggle, name="api_task_toggle"),
    path("api/tasks/clear-completed/", views.api_clear_completed, name="api_clear_completed"),
    path("api/categories/", views.api_categories, name="api_categories"),
    path("api/categories/<int:pk>/", views.api_category_detail, name="api_category_detail"),
]
