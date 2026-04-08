from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),

    path('service/', views.Service.as_view(), name='service'),
    path('product/', views.Product.as_view(), name='product'),

    path('galleries/', views.galleries, name='galleries'),
    path('galleries/<slug:slug>/', views.gallery_detail, name='gallery_detail'),

    path('video/', views.Video.as_view(), name='video'),
    path('about/', views.About.as_view(), name='about'),
    path('videoreviews/', views.videoreviews, name='videoreviews'),

    path('consultation/', views.create_lead, name='create_lead'),
    path('consultation/success/', views.create_lead_success, name='create_lead_success'),

    path('locations/', views.locations_list, name='locations_list'),
    path('locations/<slug:slug>/', views.location_detail, name='location_detail'),
    path('set-location/<slug:slug>/', views.set_location, name='set_location'),

    path('copyright/', views.CopyrightPage.as_view(), name='copyright'),
    path('terms/', views.Terms.as_view(), name='terms'),
    path('privacy/', views.Privacy.as_view(), name='privacy'),

    path('garage_cabinet', views.GarageCabinet.as_view(), name='garage_cabinet'),
    path('garage_flooring', views.GarageFlooring.as_view(), name='garage_flooring'),
    path('garage_slatwall', views.GarageSlatwall.as_view(), name='garage_slatwall'),
    path('storage_rack', views.StorageRack.as_view(), name='storage_rack'),
    path('garage_makeover', views.GarageMakeover.as_view(), name='garage_makeover'),
    path('garage_door', views.GarageDoor.as_view(), name='garage_door'),
    path('garage_conversion', views.GarageConversion.as_view(), name='garage_conversion'),
    path('car_lift', views.CarLift.as_view(), name='car_lift'),
]