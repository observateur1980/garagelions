# garagelions/urls.py — COMPLETE FILE

from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from account import views as account_views
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

    # SEO sitemap
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps},
         name='django.contrib.sitemaps.views.sitemap'),


]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)