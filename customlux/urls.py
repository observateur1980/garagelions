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

    path("p/<int:pk>/todo/add/", views.todo_add, name="todo_add"),
    path("p/<int:pk>/todo/<int:todo_pk>/toggle/", views.todo_toggle, name="todo_toggle"),
    path("p/<int:pk>/todo/<int:todo_pk>/delete/", views.todo_delete, name="todo_delete"),

    path("p/<int:pk>/customer-payment/add/", views.customer_payment_add, name="customer_payment_add"),
    path("p/<int:pk>/customer-payment/<int:pay_pk>/delete/", views.customer_payment_delete, name="customer_payment_delete"),

    path("p/<int:pk>/change/add/", views.change_order_add, name="change_order_add"),
    path("p/<int:pk>/change/<int:co_pk>/delete/", views.change_order_delete, name="change_order_delete"),

    path("p/<int:pk>/payment/add/", views.payment_add, name="payment_add"),
    path("p/<int:pk>/payment/<int:pay_pk>/delete/", views.payment_delete, name="payment_delete"),

    path("p/<int:pk>/estimate/add/", views.estimate_upload, name="estimate_upload"),
    path("p/<int:pk>/estimate/<int:est_pk>/delete/", views.estimate_delete, name="estimate_delete"),

    # Reached from /panel/ — copies a lead onto the board.
    path("send/<int:pk>/", views.send_lead, name="send_lead"),

    path("settings/", views.board_settings, name="settings"),

    path("members/", views.members, name="members"),
    path("members/<int:pk>/toggle/", views.member_toggle, name="member_toggle"),
    path("members/<int:pk>/reset/", views.member_reset_password,
         name="member_reset_password"),
    path("members/<int:pk>/remove/", views.member_remove, name="member_remove"),
]
