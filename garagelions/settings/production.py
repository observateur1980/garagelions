import os
from dotenv import load_dotenv

# Load .env FIRST
ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
load_dotenv(ENV_PATH)

from .base import *

# ----------------------------------------------------------------------
# SECURITY
# ----------------------------------------------------------------------

DEBUG = False

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise Exception("Missing DJANGO_SECRET_KEY environment variable!")

ALLOWED_HOSTS = [
    "garagelions.com",
    "www.garagelions.com",

]

# ----------------------------------------------------------------------
# Database:
# PostgreSQL in production
# SQLite fallback on local machine
# ----------------------------------------------------------------------


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "garagelions_db",
        "USER": "parviz",
        "PASSWORD": os.environ.get("DB_PASSWORD"),
        "HOST": "localhost",
        "PORT": "5432",
    }
}

# ----------------------------------------------------------------------
# Static & Media (served by Nginx)
# ----------------------------------------------------------------------


STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")

# ----------------------------------------------------------------------
# Email — SendGrid SMTP relay
# ----------------------------------------------------------------------

EMAIL_HOST_USER = "apikey"
EMAIL_HOST_PASSWORD = os.environ.get("SENDGRID_API_KEY")

# ----------------------------------------------------------------------
# Twilio SMS (optional)
# ----------------------------------------------------------------------

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "")

# ----------------------------------------------------------------------
# reCAPTCHA
# ----------------------------------------------------------------------

RECAPTCHA_PUBLIC_KEY = os.environ.get("RECAPTCHA_PUBLIC_KEY")
RECAPTCHA_PRIVATE_KEY = os.environ.get("RECAPTCHA_PRIVATE_KEY")

# ----------------------------------------------------------------------
# Security Headers
# ----------------------------------------------------------------------

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = "DENY"


CSRF_TRUSTED_ORIGINS = [
    "https://garagelions.com",
    "https://www.garagelions.com",
]

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True

SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True