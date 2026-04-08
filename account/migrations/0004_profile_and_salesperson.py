# account/migrations/0004_profile_and_salesperson.py
#
# Profile fields already exist in DB from the old 0004_profile_expanded migration.
# This migration only creates the Salesperson model.
# Profile AddField operations are wrapped in SeparateDatabaseAndState so Django
# knows about them in its state without trying to add columns that already exist.

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

        # ── Profile fields — state only (columns already in DB) ──────────
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(model_name='profile', name='photo',
                    field=models.ImageField(blank=True, null=True, upload_to=account.models.profile_photo_upload)),
                migrations.AddField(model_name='profile', name='bio',
                    field=models.TextField(blank=True)),
                migrations.AddField(model_name='profile', name='phone',
                    field=models.CharField(blank=True, max_length=30)),
                migrations.AddField(model_name='profile', name='mobile',
                    field=models.CharField(blank=True, max_length=30)),
                migrations.AddField(model_name='profile', name='direct_email',
                    field=models.EmailField(blank=True)),
                migrations.AddField(model_name='profile', name='city',
                    field=models.CharField(blank=True, max_length=100)),
                migrations.AddField(model_name='profile', name='state',
                    field=models.CharField(blank=True, max_length=100)),
                migrations.AddField(model_name='profile', name='timezone',
                    field=models.CharField(blank=True, default='America/Los_Angeles', max_length=60)),
                migrations.AddField(model_name='profile', name='linkedin_url',
                    field=models.URLField(blank=True)),
                migrations.AddField(model_name='profile', name='calendly_url',
                    field=models.URLField(blank=True)),
                migrations.AddField(model_name='profile', name='notify_new_lead_email',
                    field=models.BooleanField(default=True)),
                migrations.AddField(model_name='profile', name='notify_new_lead_sms',
                    field=models.BooleanField(default=False)),
                migrations.AddField(model_name='profile', name='updated_at',
                    field=models.DateTimeField(auto_now=True)),
            ],
            database_operations=[],  # nothing — already in DB
        ),

        # ── New fields not in DB yet ─────────────────────────────────────
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
        migrations.AlterModelOptions(
            name='profile',
            options={'verbose_name': 'Profile', 'verbose_name_plural': 'Profiles'},
        ),

        # ── Salesperson model — genuinely new ────────────────────────────
        migrations.CreateModel(
            name='Salesperson',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(
                    choices=[('salesperson','Salesperson'),('location_manager','Location Manager'),('territory_manager','Territory Manager')],
                    default='salesperson', max_length=30)),
                ('status', models.CharField(
                    choices=[('active','Active'),('on_leave','On Leave'),('terminated','Terminated')],
                    default='active', max_length=20)),
                ('employment_type', models.CharField(
                    choices=[('w2','W-2 Employee'),('1099','1099 Contractor'),('franchise_owner','Franchise Owner')],
                    default='w2', max_length=20)),
                ('base_salary', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('commission_rate', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('draw_amount', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('start_date', models.DateField(blank=True, null=True)),
                ('end_date', models.DateField(blank=True, null=True)),
                ('territory_notes', models.TextField(blank=True)),
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
                )),
                ('manager', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='direct_reports',
                    to='account.salesperson',
                )),
            ],
            options={
                'verbose_name': 'Salesperson',
                'verbose_name_plural': 'Salespeople',
                'ordering': ['user__profile__last_name', 'user__profile__first_name'],
            },
        ),
    ]