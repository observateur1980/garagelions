import os
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.conf import settings



def delete_file(file_field):
    """
    Safely delete a file from storage
    """
    if file_field and file_field.name:
        file_path = file_field.path
        if os.path.isfile(file_path):
            os.remove(file_path)


