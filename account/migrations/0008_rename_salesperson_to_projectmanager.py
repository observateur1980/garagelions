# account/migrations/0008_rename_salesperson_to_projectmanager.py
#
# Renames the Salesperson model to ProjectManager and updates:
#   - verbose_name / verbose_name_plural
#   - related_names on all FK/M2M fields
#   - role choices (adds 'project_manager', updates display labels)
#   - role field default

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0007_add_extra_sales_points'),
        ('home', '0001_initial'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='Salesperson',
            new_name='ProjectManager',
        ),
        migrations.AlterModelOptions(
            name='projectmanager',
            options={
                'ordering': ['user__profile__last_name', 'user__profile__first_name'],
                'verbose_name': 'Project Manager',
                'verbose_name_plural': 'Project Managers',
            },
        ),
        # Update related_name on OneToOneField user → project_manager
        migrations.AlterField(
            model_name='projectmanager',
            name='user',
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='project_manager',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        # Update related_name on ForeignKey sales_point → project_managers
        migrations.AlterField(
            model_name='projectmanager',
            name='sales_point',
            field=models.ForeignKey(
                blank=True,
                help_text='Primary location this person is assigned to.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='project_managers',
                to='home.salespoint',
            ),
        ),
        # Update related_name on ManyToManyField extra_sales_points → extra_project_managers
        migrations.AlterField(
            model_name='projectmanager',
            name='extra_sales_points',
            field=models.ManyToManyField(
                blank=True,
                help_text='Additional locations this person manages.',
                related_name='extra_project_managers',
                to='home.salespoint',
            ),
        ),
        # Update role choices and default value
        migrations.AlterField(
            model_name='projectmanager',
            name='role',
            field=models.CharField(
                choices=[
                    ('project_manager', 'Project Manager'),
                    ('location_manager', 'Location Manager'),
                    ('territory_manager', 'Territory Manager'),
                ],
                default='project_manager',
                max_length=30,
            ),
        ),
    ]
