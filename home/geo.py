# home/geo.py
"""
IP-based geolocation to auto-detect the customer's nearest SalesPoint.

Uses ip-api.com (free, no API key needed, 45 req/min).
Results are cached 24 hours per IP to avoid hammering the API.

Matching order:
  1. ZIP code from IP  →  ZipCode model  →  SalesPoint  (most precise)
  2. City + State      →  ServiceCity    →  SalesPoint  (fallback)
"""

import hashlib
import logging

import requests
from django.core.cache import cache

logger = logging.getLogger(__name__)

_GEO_TIMEOUT = 2       # seconds — never slow down a page load
_CACHE_TTL   = 86400   # 24 hours


def _get_client_ip(request):
    """
    Return the real client IP.
    Cloudflare always sets CF-Connecting-IP to the original visitor IP —
    use that first, then fall back to X-Forwarded-For, then REMOTE_ADDR.
    """
    # Cloudflare's header (most reliable when behind CF)
    cf_ip = request.META.get("HTTP_CF_CONNECTING_IP")
    if cf_ip:
        return cf_ip.strip()
    # Generic reverse proxy header
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _lookup_ip(ip: str) -> dict | None:
    """
    Call ip-api.com and return a dict with keys:
        zip, city, regionName (state full name), region (state abbrev)
    Returns None on any error or if the IP is private/local.
    """
    # Skip private / loopback IPs (local dev)
    if not ip or ip in ("127.0.0.1", "::1") or ip.startswith("192.168.") or ip.startswith("10."):
        return None

    cache_key = "geoip_" + hashlib.md5(ip.encode()).hexdigest()
    cached = cache.get(cache_key)
    if cached is not None:
        return cached or None   # False cached as "not found"

    try:
        resp = requests.get(
            f"http://ip-api.com/json/{ip}",
            params={"fields": "status,zip,city,regionName,region"},
            timeout=_GEO_TIMEOUT,
        )
        data = resp.json()
    except Exception as exc:
        logger.debug("ip-api.com lookup failed for %s: %s", ip, exc)
        return None

    if data.get("status") != "success":
        cache.set(cache_key, False, _CACHE_TTL)
        return None

    result = {
        "zip":   data.get("zip", ""),
        "city":  data.get("city", ""),
        "state": data.get("regionName", ""),       # full state name  e.g. "California"
        "state_abbrev": data.get("region", ""),    # abbreviation     e.g. "CA"
    }
    cache.set(cache_key, result, _CACHE_TTL)
    return result


def detect_sales_point(request):
    """
    Try to find the best matching SalesPoint for the current visitor's IP.
    Returns a SalesPoint instance or None.

    Does NOT set the session — caller decides whether to apply it.
    """
    from home.models import ZipCode, ServiceCity, SalesPoint

    ip = _get_client_ip(request)
    geo = _lookup_ip(ip)
    if not geo:
        return None

    # ── Pass 1: match by ZIP code ──────────────────────────────────────────
    if geo["zip"]:
        matched = (
            ZipCode.objects
            .select_related("service_city__sales_point")
            .filter(
                code=geo["zip"],
                service_city__is_active=True,
                service_city__sales_point__is_active=True,
            )
            .first()
        )
        if matched:
            logger.debug("GeoIP: ZIP %s → %s", geo["zip"], matched.service_city.sales_point)
            return matched.service_city.sales_point

    # ── Pass 2: match by city + state name ────────────────────────────────
    if geo["city"] and geo["state"]:
        city_match = (
            ServiceCity.objects
            .select_related("sales_point")
            .filter(
                name__iexact=geo["city"],
                is_active=True,
                sales_point__is_active=True,
            )
            .filter(
                # Try full state name first, then abbreviation
                state__iexact=geo["state"]
            )
            .first()
        )
        if not city_match and geo["state_abbrev"]:
            city_match = (
                ServiceCity.objects
                .select_related("sales_point")
                .filter(
                    name__iexact=geo["city"],
                    state__iexact=geo["state_abbrev"],
                    is_active=True,
                    sales_point__is_active=True,
                )
                .first()
            )
        if city_match:
            logger.debug("GeoIP: city %s, %s → %s", geo["city"], geo["state"], city_match.sales_point)
            return city_match.sales_point

    logger.debug("GeoIP: no match for IP %s (zip=%s, city=%s, state=%s)", ip, geo["zip"], geo["city"], geo["state"])
    return None


def auto_set_location(request):
    """
    Call this in a view to auto-detect and store the visitor's SalesPoint
    in the session. Only runs once per session (won't override a manual pick).

    Returns the detected SalesPoint or None.
    """
    # Already set (manually or previously auto-detected) — don't override
    if request.session.get("selected_sales_point_slug"):
        return None

    sales_point = detect_sales_point(request)
    if sales_point:
        request.session["selected_sales_point_slug"] = sales_point.slug
        request.session["location_auto_detected"] = True   # flag for banner
    return sales_point