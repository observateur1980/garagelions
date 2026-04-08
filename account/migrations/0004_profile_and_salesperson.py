# account/migrations/0004_profile_and_salesperson.py
# Expands Profile with all personal fields.
# Adds the new Salesperson model.
# Safe to run against a database that has existing Profile rows with null first_name/last_name.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import account.models


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0003_myuser_groups_myuser_is_superuser_and_more'),
        ('home', '0003_remove_leadmodel_name_leadmodel_first_name_and_more'),
    ]

    operations = [

        # ── Profile expansions ──────────────────────────────────────────

        migrations.AddField(
            model_name='profile',
            name='photo',
            field=models.ImageField(
                blank=True, null=True,
                upload_to=account.models.profile_photo_upload,
            ),
        ),
        migrations.AddField(
            model_name='profile',
            name='bio',
            field=models.TextField(blank=True, help_text='Short personal bio — not visible to customers.'),
        ),
        migrations.AddField(
            model_name='profile',
            name='phone',
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name='profile',
            name='mobile',
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name='profile',
            name='direct_email',
            field=models.EmailField(blank=True, help_text='Work email if different from login email.'),
        ),
        migrations.AddField(
            model_name='profile',
            name='city',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='profile',
            name='state',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='profile',
            name='timezone',
            field=models.CharField(blank=True, default='America/Los_Angeles', max_length=60),
        ),
        migrations.AddField(
            model_name='profile',
            name='linkedin_url',
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='calendly_url',
            field=models.URLField(blank=True, help_text='Calendly or Cal.com booking link.'),
        ),
        migrations.AddField(
            model_name='profile',
            name='notify_new_lead_email',
            field=models.BooleanField(default=True, help_text='Email me when a new lead is assigned.'),
        ),
        migrations.AddField(
            model_name='profile',
            name='notify_new_lead_sms',
            field=models.BooleanField(default=False, help_text='SMS me when a new lead is assigned.'),
        ),
        migrations.AddField(
            model_name='profile',
            name='emergency_contact_name',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='profile',
            name='emergency_contact_phone',
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name='profile',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterModelOptions(
            name='profile',
            options={'verbose_name': 'Profile', 'verbose_name_plural': 'Profiles'},
        ),

        # ── Salesperson model ───────────────────────────────────────────

        migrations.CreateModel(
            name='Salesperson',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(
                    choices=[
                        ('salesperson', 'Salesperson'),
                        ('location_manager', 'Location Manager'),
                        ('territory_manager', 'Territory Manager'),
                    ],
                    default='salesperson',
                    max_length=30,
                )),
                ('status', models.CharField(
                    choices=[
                        ('active', 'Active'),
                        ('on_leave', 'On Leave'),
                        ('terminated', 'Terminated'),
                    ],
                    default='active',
                    max_length=20,
                )),
                ('employment_type', models.CharField(
                    choices=[
                        ('w2', 'W-2 Employee'),
                        ('1099', '1099 Contractor'),
                        ('franchise_owner', 'Franchise Owner'),
                    ],
                    default='w2',
                    max_length=20,
                )),
                ('base_salary', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=10, null=True,
                    help_text='Annual base salary in USD (if applicable).',
                )),
                ('commission_rate', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=5, null=True,
                    help_text='Commission percentage on closed deals (e.g. 5.00 = 5%).',
                )),
                ('draw_amount', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=10, null=True,
                    help_text='Monthly draw against commission (if applicable).',
                )),
                ('start_date', models.DateField(blank=True, null=True)),
                ('end_date', models.DateField(
                    blank=True, null=True,
                    help_text='Leave blank if currently active.',
                )),
                ('territory_notes', models.TextField(
                    blank=True,
                    help_text='For territory managers: description of their oversight area.',
                )),
                ('internal_notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='salesperson',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('sales_point', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='salespeople',
                    to='home.salespoint',
                    help_text='Primary location this person is assigned to.',
                )),
                ('manager', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='direct_reports',
                    to='account.salesperson',
                    help_text='Who this person reports to.',
                )),
            ],
            options={
                'verbose_name': 'Salesperson',
                'verbose_name_plural': 'Salespeople',
                'ordering': ['user__profile__last_name', 'user__profile__first_name'],
            },
        ),
    ]