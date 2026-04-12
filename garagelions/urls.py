# garagelions/urls.py — COMPLETE FILE

from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from account import views as account_views
from home import views_sales
from home.sitemaps import StaticViewSitemap, LocationSitemap, GallerySitemap

sitemaps = {
    'static':    StaticViewSitemap,
    'locations': LocationSitemap,
    'galleries': GallerySitemap,
}

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('home.urls')),
    path('account/', include('account.urls', namespace='account')),

    # Auth shortcuts
    path('login/',  account_views.user_login,  name='login_shortcut'),
    path('logout/', account_views.user_logout, name='logout_shortcut'),

    # ── Sales CRM ────────────────────────────────────────────────────────
    # Salesperson dashboard (default — all logged-in users land here)
    path('sales/dashboard/',
         views_sales.sales_dashboard,
         name='sales_dashboard'),

    # Location Manager dashboard
    path('sales/dashboard/manager/',
         views_sales.sales_dashboard_manager,
         name='sales_dashboard_manager'),

    # Territory Manager dashboard
    path('sales/dashboard/territory/',
         views_sales.sales_dashboard_territory,
         name='sales_dashboard_territory'),

    # Shared lead list + detail
    path('sales/leads/',
         views_sales.sales_lead_list,
         name='sales_lead_list'),
    path('sales/leads/<int:pk>/',
         views_sales.sales_lead_detail,
         name='sales_lead_detail'),

    path('sales/leads/add/', views_sales.sales_lead_create, name='sales_lead_create'),

    # Estimates
    path('sales/leads/<int:lead_pk>/estimate/new/',
         views_sales.estimate_edit,
         name='estimate_new'),
    path('sales/leads/<int:lead_pk>/estimate/<int:pk>/',
         views_sales.estimate_edit,
         name='estimate_edit'),

    # SEO sitemap
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps},
         name='django.contrib.sitemaps.views.sitemap'),


]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)