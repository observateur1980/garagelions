"""
Management command: send_stale_lead_reminders

Finds leads that are still "new" after a configurable number of hours and
sends a reminder email (and optionally SMS) to the assigned salesperson.

Usage:
    python manage.py send_stale_lead_reminders           # default: 24 hours
    python manage.py send_stale_lead_reminders --hours 48

Recommended: run via server cron every hour.
  0 * * * * /path/to/venv/bin/python /path/to/manage.py send_stale_lead_reminders >> /var/log/gl_reminders.log 2>&1
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils.timezone import now

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Email/SMS salesperson when their leads stay 'new' past a threshold."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=24,
            help="Age threshold in hours (default: 24).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be sent without actually sending.",
        )

    def handle(self, *args, **options):
        from home.models import LeadModel, LeadActivity
        from home.notifications import notify_new_lead_to_salesperson, _send_sms

        hours = options["hours"]
        dry_run = options["dry_run"]
        threshold = now() - timedelta(hours=hours)

        # Find stale leads that haven't already had a reminder sent
        stale_leads = (
            LeadModel.objects.filter(status="new", created_at__lte=threshold)
            .exclude(activities__action=LeadActivity.ACTION_REMINDER)
            .select_related(
                "assigned_user",
                "assigned_user__profile",
                "sales_point",
                "service_city",
            )
        )

        count = stale_leads.count()
        if count == 0:
            self.stdout.write("No stale leads found.")
            return

        self.stdout.write(f"Found {count} stale lead(s) (>{hours}h, still new).")

        for lead in stale_leads:
            assigned = lead.assigned_user
            if not assigned:
                self.stdout.write(f"  Lead #{lead.pk} has no assigned user — skipped.")
                continue

            try:
                profile = assigned.profile
            except Exception:
                profile = None

            salesperson_phone = getattr(profile, "display_phone", None) if profile else None
            salesperson_email = (
                getattr(profile, "display_email", None) if profile else None
            ) or assigned.email

            self.stdout.write(
                f"  Lead #{lead.pk} — {lead.first_name} {lead.last_name} "
                f"({lead.zip_code}) — assigned to {assigned.get_full_name()} "
                f"<{salesperson_email}>"
            )

            if dry_run:
                self.stdout.write("    [DRY RUN] Would send reminder — skipping.")
                continue

            # Send reminder email using the salesperson notification
            # (reuses the same HTML template, subject updated below)
            from django.conf import settings
            from django.core.mail import EmailMultiAlternatives

            crm_url = f"https://garagelions.com/sales/leads/{lead.pk}/"
            hours_old = int((now() - lead.created_at).total_seconds() // 3600)
            subject = (
                f"REMINDER: Uncontacted Lead — {lead.first_name} {lead.last_name} "
                f"({hours_old}h old)"
            )
            body = (
                f"Hi {assigned.get_short_name()},\n\n"
                f"This is a friendly reminder that the following lead has been "
                f"waiting for contact for {hours_old} hours and is still marked as 'New'.\n\n"
                f"Name:     {lead.first_name} {lead.last_name}\n"
                f"Phone:    {lead.phone}\n"
                f"Email:    {lead.email}\n"
                f"ZIP:      {lead.zip_code}\n"
                f"Services: {', '.join(lead.consultation_types) if lead.consultation_types else 'N/A'}\n\n"
                f"Please reach out to this customer as soon as possible!\n\n"
                f"View in CRM: {crm_url}\n\n"
                f"— Garage Lions CRM\n"
            )

            try:
                EmailMultiAlternatives(
                    subject=subject,
                    body=body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[salesperson_email],
                    reply_to=[lead.email] if lead.email else [],
                ).send(fail_silently=False)
                self.stdout.write(f"    Email reminder sent to {salesperson_email}.")
            except Exception as exc:
                self.stderr.write(f"    Email failed: {exc}")

            # SMS reminder
            send_sms = getattr(profile, "notify_new_lead_sms", False)
            if send_sms and salesperson_phone:
                sms_body = (
                    f"GL REMINDER: Lead #{lead.pk} {lead.first_name} {lead.last_name} "
                    f"still uncontacted ({hours_old}h) | {lead.phone} | {crm_url}"
                )
                if _send_sms(salesperson_phone, sms_body):
                    self.stdout.write(f"    SMS reminder sent.")

            # Record in activity log
            LeadActivity.objects.create(
                lead=lead,
                user=None,
                action=LeadActivity.ACTION_REMINDER,
                detail=f"Stale lead reminder sent to {assigned.get_full_name()} after {hours_old}h.",
            )

        self.stdout.write(self.style.SUCCESS(f"Done. Processed {count} lead(s)."))