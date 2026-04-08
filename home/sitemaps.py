# home/sitemaps.py
# -----------------------------------------------------------------------
# Django sitemap framework for Garage Lions.
# Generates location-specific sitemap entries for Google indexing.
#
# SETUP:
# 1. Add 'django.contrib.sitemaps' to INSTALLED_APPS in settings/base.py
# 2. Add the sitemap URL to garagelions/urls.py (see bottom of this file)
# -----------------------------------------------------------------------

from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from .models import Gallery, SalesPoint


class StaticViewSitemap(Sitemap):
    priority = 0.5
    changefreq = "monthly"

    def items(self):
        return [
            "home", "service", "product", "galleries", "about",
            "locations_list", "videoreviews",
            "garage_cabinet", "garage_flooring", "garage_slatwall",
            "storage_rack", "garage_makeover", "garage_door",
            "garage_conversion", "car_lift",
        ]

    def location(self, item):
        return reverse(item)


class LocationSitemap(Sitemap):
    """One entry per active SalesPoint location page."""
    priority = 0.9
    changefreq = "weekly"

    def items(self):
        return SalesPoint.objects.filter(is_active=True).order_by("order", "name")

    def location(self, obj):
        return reverse("location_detail", args=[obj.slug])


class GallerySitemap(Sitemap):
    priority = 0.6
    changefreq = "weekly"

    def items(self):
        return Gallery.objects.filter(is_active=True).order_by("order", "name")

    def location(self, obj):
        return reverse("gallery_detail", args=[obj.slug])


# -----------------------------------------------------------------------
# ADD to garagelions/urls.py:
# -----------------------------------------------------------------------
#
# from django.contrib.sitemaps.views import sitemap
# from home.sitemaps import StaticViewSitemap, LocationSitemap, GallerySitemap
#
# sitemaps = {
#     "static": StaticViewSitemap,
#     "locations": LocationSitemap,
#     "galleries": GallerySitemap,
# }
#
# urlpatterns = [
#     ...
#     path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="django.contrib.sitemaps.views.sitemap"),
# ]