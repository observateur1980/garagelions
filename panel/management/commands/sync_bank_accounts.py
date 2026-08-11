"""
Management command: sync_bank_accounts

Pulls new/changed transactions from every linked Plaid item into
BankTransaction. This is the safety net behind the Plaid webhook — if a webhook
is missed (or webhooks aren't configured at all), the feed still catches up.

Items flagged needs_reauth are skipped: the bank is refusing us until the user
signs in again through Link's update mode, so calling would only burn requests.

Usage:
    venv/bin/python manage.py sync_bank_accounts
    venv/bin/python manage.py sync_bank_accounts --dry-run
    venv/bin/python manage.py sync_bank_accounts --item <item_id>

Recommended: run via cron a few times a day — transactions post slowly and
Plaid rate-limits per item.
  17 */4 * * * cd /var/www/garagelions && venv/bin/python manage.py sync_bank_accounts >> logs/bank_sync.log 2>&1
"""

import logging

import plaid
from django.core.management.base import BaseCommand
from django.utils.timezone import now

from panel.models import PlaidItem

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Pull new bank transactions for every linked Plaid connection."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="List what would be synced without calling Plaid.",
        )
        parser.add_argument(
            "--item", default="",
            help="Sync only this Plaid item_id.",
        )

    def handle(self, *args, **options):
        # Imported here so the command still loads if plaid_client can't build
        # a client (e.g. keys missing on a dev box).
        from panel.plaid_client import is_configured
        from panel.views import _sync_item

        if not is_configured():
            self.stderr.write("Plaid is not configured — nothing to sync.")
            return

        items = PlaidItem.objects.all()
        if options["item"]:
            items = items.filter(item_id=options["item"])

        total_new = 0
        for item in items:
            label = item.institution_name or item.item_id
            if item.needs_reauth:
                self.stdout.write(f"skip   {label} — needs re-authentication")
                continue
            if options["dry_run"]:
                self.stdout.write(f"would sync {label} (last: {item.last_synced})")
                continue
            try:
                n = _sync_item(item)
            except plaid.ApiException as e:
                code = ""
                try:
                    import json
                    code = json.loads(e.body).get("error_code", "")
                except Exception:
                    pass
                if code in ("ITEM_LOGIN_REQUIRED", "PENDING_EXPIRATION"):
                    item.needs_reauth = True
                    item.save(update_fields=["needs_reauth"])
                    self.stderr.write(f"reauth {label} — bank wants a fresh sign-in")
                else:
                    logger.exception("Plaid sync failed for %s", item.item_id)
                    self.stderr.write(f"error  {label} — {code or 'see log'}")
                continue
            total_new += n
            self.stdout.write(f"ok     {label} — {n} new")

        self.stdout.write(f"[{now():%Y-%m-%d %H:%M}] done, {total_new} new transaction(s)")
