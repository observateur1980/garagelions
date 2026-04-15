# account/migrations/0009_update_role_project_manager.py
#
# Data migration: updates existing rows where role='salesperson'
# to the new value 'project_manager'.

from django.db import migrations


def forwards(apps, schema_editor):
    ProjectManager = apps.get_model('account', 'ProjectManager')
    ProjectManager.objects.filter(role='salesperson').update(role='project_manager')


def backwards(apps, schema_editor):
    ProjectManager = apps.get_model('account', 'ProjectManager')
    ProjectManager.objects.filter(role='project_manager').update(role='salesperson')


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0008_rename_salesperson_to_projectmanager'),
    ]

    operations = [
        migrations.RunPython(forwards, reverse_code=backwards),
    ]
