import os
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.conf import settings

from .models import (
    Project,
    ProjectBeforeImage,
    ProjectConstructionImage,
    ProjectAfterImage,
)


def delete_file(file_field):
    """
    Safely delete a file from storage
    """
    if file_field and file_field.name:
        file_path = file_field.path
        if os.path.isfile(file_path):
            os.remove(file_path)


@receiver(post_delete, sender=ProjectBeforeImage)
def delete_before_image_file(sender, instance, **kwargs):
    delete_file(instance.image)


@receiver(post_delete, sender=ProjectConstructionImage)
def delete_construction_image_file(sender, instance, **kwargs):
    delete_file(instance.image)


@receiver(post_delete, sender=ProjectAfterImage)
def delete_after_image_file(sender, instance, **kwargs):
    delete_file(instance.image)


@receiver(post_delete, sender=Project)
def delete_project_cover_and_folder(sender, instance, **kwargs):
    # delete cover image
    delete_file(instance.cover_image)

    # try to remove empty project folder
    project_dir = os.path.join(settings.MEDIA_ROOT, "projects", instance.slug)
    if os.path.isdir(project_dir):
        try:
            os.rmdir(project_dir)  # only removes if empty
        except OSError:
            pass
