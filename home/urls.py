from django.urls import path
from . import views



urlpatterns = [
    path("", views.home, name="home"),

    # PROJECTS
    path("projects/", views.projects, name="projects"),
    path("projects/<slug:slug>/", views.project_detail, name="project_detail"),

    # STATIC PAGES
    path("video/", views.Video.as_view(), name="video"),


    path("new-construction/", views.Newconstruction.as_view(), name="newconstruction"),
    path("kitchen_remodeling/", views.KitchenRemodeling.as_view(), name="kitchen_remodeling"),
    path("bathroom/", views.Bathroom.as_view(), name="bathroom"),
    path("garage/", views.Garage.as_view(), name="garage"),
    path("home-remodel/", views.Homeremodel.as_view(), name="homeremodel"),
    path("home-additions/", views.Homeadditions.as_view(), name="homeadditions"),

    path("videoreviews/", views.videoreviews, name="videoreviews"),

    # LEADS
    path("contact/", views.create_lead, name="create_lead"),
    path("contact/success/", views.create_lead_success, name="create_lead_success"),


    path("copyright/", views.CopyrightPage.as_view(), name="copyright"),
    path("terms/", views.Terms.as_view(), name="terms"),
    path("privacy/", views.Privacy.as_view(), name="privacy"),
]