import os
import logging

from django.db.models.signals import post_delete, pre_save, post_save
from django.dispatch import receiver
from django.conf import settings

logger = logging.getLogger(__name__)


def delete_file(file_field):
    """Safely delete a file from storage."""
    if file_field and file_field.name:
        file_path = file_field.path
        if os.path.isfile(file_path):
            os.remove(file_path)


# ---------------------------------------------------------------------------
# Lead reassignment detection
# ---------------------------------------------------------------------------

@receiver(pre_save, sender="home.LeadModel")
def track_lead_reassignment(sender, instance, **kwargs):
    """
    Before saving a lead, snapshot the current assigned_user so post_save
    can detect a change and send a reassignment notification.
    """
    if not instance.pk:
        instance._prev_assigned_user_id = None
        return
    try:
        old = sender.objects.only("assigned_user_id").get(pk=instance.pk)
        instance._prev_assigned_user_id = old.assigned_user_id
    except sender.DoesNotExist:
        instance._prev_assigned_user_id = None


@receiver(post_save, sender="home.LeadModel")
def notify_on_reassignment(sender, instance, created, **kwargs):
    """
    After a lead is saved, if the assigned_user changed (and this isn't a new
    lead — new leads are handled in create_lead view), send a notification
    to the newly assigned salesperson.
    """
    if created:
        return  # handled in views.py

    prev_id = getattr(instance, "_prev_assigned_user_id", None)
    new_id = instance.assigned_user_id

    if new_id and new_id != prev_id:
        from home.notifications import notify_lead_reassigned
        from home.models import LeadActivity
        try:
            notify_lead_reassigned(instance, instance.assigned_user)
            LeadActivity.objects.create(
                lead=instance,
                user=None,
                action=LeadActivity.ACTION_ASSIGNED,
                detail=(
                    f"Reassigned to {instance.assigned_user.get_full_name() or instance.assigned_user.username}"
                ),
            )
        except Exception as exc:
            logger.error("Reassignment notification failed for lead #%s: %s", instance.pk, exc)