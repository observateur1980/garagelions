# garagelions/urls.py — COMPLETE FILE

from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from account import views as account_views
from home import views as home_views
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

    # ── Panel (internal admin) ───────────────────────────────────────────
    path('panel/', include('panel.urls', namespace='panel')),

    # ── Task Board (standalone) ──────────────────────────────────────────
    path('taskboard/', include('taskboard.urls', namespace='taskboard')),

    # SEO sitemap
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps},
         name='django.contrib.sitemaps.views.sitemap'),

    # ── PWA (iPhone "Add to Home Screen") ────────────────────────────────
    path('manifest.webmanifest', home_views.pwa_manifest, name='pwa_manifest'),
    path('sw.js', home_views.pwa_service_worker, name='pwa_service_worker'),

    # ── Web Push subscription endpoints ──────────────────────────────────
    path('push/vapid-key/', home_views.push_vapid_public_key, name='push_vapid_key'),
    path('push/subscribe/', home_views.push_subscribe, name='push_subscribe'),
    path('push/unsubscribe/', home_views.push_unsubscribe, name='push_unsubscribe'),
    path('push/test/', home_views.push_test, name='push_test'),

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)