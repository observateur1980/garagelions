from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('home', '0004_franchiseagreement_remove_leadmodel_assigned_to_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='LeadActivity',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(
                    choices=[
                        ('created', 'Lead Created'),
                        ('status_changed', 'Status Changed'),
                        ('notes_updated', 'Notes Updated'),
                        ('assigned', 'Reassigned'),
                        ('reminder_sent', 'Stale Reminder Sent'),
                    ],
                    max_length=30,
                )),
                ('detail', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('lead', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='activities',
                    to='home.leadmodel',
                )),
                ('user', models.ForeignKey(
                    blank=True,
                    help_text='Who triggered this event (null = system/automated).',
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='lead_activities',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Lead Activity',
                'verbose_name_plural': 'Lead Activities',
                'ordering': ['-created_at'],
            },
        ),
    ]