"""End-to-end push diagnostic.

Run with the project's venv:
    /var/www/garagelions/venv/bin/python check_push.py

Prints the current PushSubscription state and tries to send a test push
to each subscribed user using the same code path as follow-up reminders.
"""
import django
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "garagelions.settings")
django.setup()

from django.conf import settings
from home.models import PushSubscription
from home.notifications import send_push_to_user


print("=== VAPID config ===")
print(f"  PUB len:   {len(settings.VAPID_PUBLIC_KEY)}")
print(f"  PRIV len:  {len(settings.VAPID_PRIVATE_KEY)}")
print(f"  ADMIN:     {settings.VAPID_ADMIN_EMAIL}")

print()
print("=== Subscriptions ===")
subs = list(PushSubscription.objects.select_related("user"))
print(f"  Total rows: {len(subs)}")
for s in subs:
    host = s.endpoint.split("/")[2] if "://" in s.endpoint else "?"
    print(f"  - user={s.user} (id={s.user_id}) | host={host} | last_used={s.last_used_at}")

if not subs:
    print()
    print("  >>> NO SUBSCRIPTIONS IN DB. <<<")
    print("  The phone has never registered (or registrations were wiped).")
    print("  Fix: open the PWA from the home-screen icon, go to /panel/m/leads/,")
    print("  tap Disable then Enable then Test.")
else:
    print()
    print("=== Sending direct test push to each subscribed user ===")
    seen = set()
    for s in subs:
        if s.user_id in seen:
            continue
        seen.add(s.user_id)
        sent, failed = send_push_to_user(
            s.user,
            title="Direct test from check_push.py",
            body="If you see this, push works.",
        )
        print(f"  -> {s.user}: sent={sent}, failed={failed}")

    print()
    print("If sent>0 but no notification arrived on phone, the OS/browser dropped it.")
    print("Common causes: PWA not installed on home screen, notif permission denied,")
    print("or iOS < 16.4. Re-add to home screen and re-grant permission.")
