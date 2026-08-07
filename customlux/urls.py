from django.urls import path

from . import views

app_name = "customlux"

urlpatterns = [
    path("", views.board, name="board"),
    path("archived/", views.archived, name="archived"),

    path("new/", views.project_create, name="project_create"),
    path("p/<int:pk>/", views.project_detail, name="project_detail"),
    path("p/<int:pk>/move/", views.project_move, name="project_move"),
    path("p/<int:pk>/archive/", views.project_archive, name="project_archive"),

    # Reached from /panel/ — copies a lead onto the board.
    path("send/<int:pk>/", views.send_lead, name="send_lead"),

    path("members/", views.members, name="members"),
    path("members/<int:pk>/toggle/", views.member_toggle, name="member_toggle"),
    path("members/<int:pk>/remove/", views.member_remove, name="member_remove"),
]
