"""Google Calendar OAuth + event-fetching helpers.

Per-user OAuth: each staff member connects their own Google account; tokens
are stored in panel.models.GoogleCalendarCredential. Read-only scope —
we only fetch events to seed leads, never write back.
"""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from .models import GoogleCalendarCredential


SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/calendar.readonly",
]


def is_configured():
    return bool(settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET)


def _client_config():
    return {
        "web": {
            "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.GOOGLE_OAUTH_REDIRECT_URI],
        }
    }


def build_flow(state=None):
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=settings.GOOGLE_OAUTH_REDIRECT_URI,
        state=state,
    )
    return flow


def save_credentials(user, creds, google_email=""):
    obj, _ = GoogleCalendarCredential.objects.update_or_create(
        user=user,
        defaults={
            "google_email": google_email,
            "access_token": creds.token or "",
            "refresh_token": creds.refresh_token or "",
            "token_uri": creds.token_uri or "https://oauth2.googleapis.com/token",
            "scopes": " ".join(creds.scopes or []),
            "expiry": creds.expiry if creds.expiry else None,
        },
    )
    return obj


def credentials_for_user(user):
    try:
        rec = user.gcal_credential
    except GoogleCalendarCredential.DoesNotExist:
        return None
    return Credentials(
        token=rec.access_token,
        refresh_token=rec.refresh_token or None,
        token_uri=rec.token_uri,
        client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
        client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
        scopes=rec.scopes.split() if rec.scopes else SCOPES,
    )


def fetch_userinfo_email(creds):
    """One-shot call right after OAuth to record which Google account
    was connected."""
    try:
        service = build("oauth2", "v2", credentials=creds, cache_discovery=False)
        info = service.userinfo().get().execute()
        return info.get("email", "")
    except Exception:
        return ""


LEADS_CALENDAR_NAME = "Leads"


def _pick_calendar_id(service):
    """Prefer a calendar named "Leads" (case-insensitive); fall back to primary."""
    try:
        resp = service.calendarList().list(maxResults=250).execute()
    except Exception:
        return "primary", "primary"
    target = LEADS_CALENDAR_NAME.casefold()
    for cal in resp.get("items", []):
        if (cal.get("summary") or "").casefold() == target:
            return cal["id"], cal.get("summary") or "Leads"
    for cal in resp.get("items", []):
        if cal.get("primary"):
            return cal["id"], cal.get("summary") or "primary"
    return "primary", "primary"


def fetch_upcoming_events(user, days_ahead=30, max_results=50):
    creds = credentials_for_user(user)
    if creds is None:
        return [], ""
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    calendar_id, calendar_name = _pick_calendar_id(service)
    now = timezone.now()
    end = now + timedelta(days=days_ahead)
    resp = service.events().list(
        calendarId=calendar_id,
        timeMin=now.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
        maxResults=max_results,
    ).execute()
    # Persist refreshed token if it changed during this call
    if creds.token and creds.token != user.gcal_credential.access_token:
        user.gcal_credential.access_token = creds.token
        if creds.expiry:
            user.gcal_credential.expiry = creds.expiry
        user.gcal_credential.save(update_fields=["access_token", "expiry", "updated_at"])
    return resp.get("items", []), calendar_name


def event_source_tag(event_id):
    """How we mark a Lead's source_page so we can detect already-imported events."""
    return f"google_calendar:{event_id}"
