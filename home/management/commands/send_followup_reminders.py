"""
Management command: send_followup_reminders

Delivers any LeadFollowUp reminders whose remind_at <= now and is_sent=False.
Sends push (PWA) + email + SMS to the assigned salesperson and the user who
created the reminder.

Usage:
    python manage.py send_followup_reminders
    python manage.py send_followup_reminders --dry-run

Recommended: run via cron every minute (or every few minutes).
  * * * * * /path/to/venv/bin/python /path/to/manage.py send_followup_reminders >> /var/log/gl_followups.log 2>&1
"""

import logging

from django.core.management.base import BaseCommand
from django.utils.timezone import now

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Deliver any due follow-up reminders for leads."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be sent without actually sending.",
        )

    def handle(self, *args, **options):
        from home.models import LeadFollowUp
        from home.notifications import notify_followup_reminder

        dry_run = options["dry_run"]
        due = (
            LeadFollowUp.objects
            .filter(is_sent=False, remind_at__lte=now())
            .select_related(
                "lead",
                "lead__assigned_user",
                "lead__assigned_user__profile",
                "created_by",
                "created_by__profile",
            )
        )

        count = due.count()
        if count == 0:
            self.stdout.write("No follow-up reminders due.")
            return

        self.stdout.write(f"Found {count} due follow-up reminder(s).")

        for fu in due:
            lead = fu.lead
            self.stdout.write(
                f"  Reminder #{fu.pk} — Lead #{lead.pk} {lead.first_name} {lead.last_name} "
                f"(scheduled {fu.remind_at:%Y-%m-%d %H:%M})"
            )
            if dry_run:
                self.stdout.write("    [DRY RUN] Would send — skipping.")
                continue
            try:
                notify_followup_reminder(fu)
                fu.is_sent = True
                fu.sent_at = now()
                fu.save(update_fields=["is_sent", "sent_at"])
                self.stdout.write("    Sent.")
            except Exception as exc:
                logger.exception("Failed to send follow-up reminder #%s", fu.pk)
                self.stderr.write(f"    Failed: {exc}")

        self.stdout.write(self.style.SUCCESS(f"Done. Processed {count} reminder(s)."))
