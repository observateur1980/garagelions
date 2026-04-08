# account/migrations/0004_profile_expanded.py
# Run: python manage.py migrate

from django.db import migrations, models
import account.models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0003_myuser_groups_myuser_is_superuser_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="job_title",
            field=models.CharField(blank=True, max_length=120, help_text="e.g. Sales Manager, Lead Consultant"),
        ),
        migrations.AddField(
            model_name="profile",
            name="photo",
            field=models.ImageField(blank=True, null=True, upload_to=account.models.profile_photo_upload_to),
        ),
        migrations.AddField(
            model_name="profile",
            name="bio",
            field=models.TextField(blank=True, help_text="Short bio shown on profile page"),
        ),
        migrations.AddField(
            model_name="profile",
            name="phone",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="profile",
            name="mobile",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="profile",
            name="direct_email",
            field=models.EmailField(blank=True, help_text="Personal work email (if different from login email)"),
        ),
        migrations.AddField(
            model_name="profile",
            name="city",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="profile",
            name="state",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="profile",
            name="timezone",
            field=models.CharField(
                blank=True, default="America/Los_Angeles", max_length=60,
                help_text="e.g. America/New_York, America/Chicago, America/Denver, America/Los_Angeles"
            ),
        ),
        migrations.AddField(
            model_name="profile",
            name="linkedin_url",
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name="profile",
            name="calendly_url",
            field=models.URLField(blank=True, help_text="Booking link (Calendly, Cal.com, etc.)"),
        ),
        migrations.AddField(
            model_name="profile",
            name="notify_new_lead_email",
            field=models.BooleanField(default=True, help_text="Email me when a new lead is assigned"),
        ),
        migrations.AddField(
            model_name="profile",
            name="notify_new_lead_sms",
            field=models.BooleanField(default=False, help_text="SMS me when a new lead is assigned"),
        ),
        migrations.AddField(
            model_name="profile",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        # Keep null=True so existing NULL rows in the DB don't violate the constraint.
        # The model uses blank=True so the form never submits NULL — DB NULLs
        # only exist in old rows and will be overwritten when each user saves their profile.
        migrations.AlterField(
            model_name="profile",
            name="first_name",
            field=models.CharField(blank=True, null=True, max_length=120),
        ),
        migrations.AlterField(
            model_name="profile",
            name="last_name",
            field=models.CharField(blank=True, null=True, max_length=120),
        ),
    ]