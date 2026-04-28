from django.db import migrations, models


SEED_STATUSES = [
    # (code, label, order, is_protected)
    ("new",                  "New",                  10, True),
    ("contacted",            "Contacted",            20, False),
    ("appointment_set",      "Appointment Set",      30, False),
    ("quoted",               "Quoted",               40, False),
    ("waiting_for_estimate", "Waiting For Estimate", 50, False),
    ("follow_up",            "Follow Up",            60, False),
    ("closed_won",           "Closed Won",           70, True),
    ("closed_lost",          "Closed Lost",          80, True),
]


def seed_statuses(apps, schema_editor):
    LeadStatus = apps.get_model("home", "LeadStatus")
    for code, label, order, is_protected in SEED_STATUSES:
        LeadStatus.objects.update_or_create(
            code=code,
            defaults={"label": label, "order": order, "is_protected": is_protected},
        )


def unseed_statuses(apps, schema_editor):
    LeadStatus = apps.get_model("home", "LeadStatus")
    LeadStatus.objects.filter(code__in=[c for c, *_ in SEED_STATUSES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("home", "0010_leadtodo"),
    ]

    operations = [
        migrations.CreateModel(
            name="LeadStatus",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=30, unique=True)),
                ("label", models.CharField(max_length=80)),
                ("order", models.PositiveIntegerField(default=100)),
                ("is_protected", models.BooleanField(
                    default=False,
                    help_text="Protected statuses are referenced by code elsewhere in the app and cannot be removed.",
                )),
            ],
            options={
                "verbose_name": "Lead status",
                "verbose_name_plural": "Lead statuses",
                "ordering": ["order", "label"],
            },
        ),
        migrations.RunPython(seed_statuses, unseed_statuses),
    ]
