from django.db import migrations, models


# Sensible color defaults for the originally-seeded statuses.
# Anything not listed defaults to "gray" (the field default).
SEED_COLORS = {
    "new":                  "blue",
    "contacted":            "amber",
    "appointment_set":      "violet",
    "quoted":               "orange",
    "waiting_for_estimate": "amber",
    "follow_up":            "teal",
    "closed_won":           "green",
    "closed_lost":          "red",
}


def seed_colors(apps, schema_editor):
    LeadStatus = apps.get_model("home", "LeadStatus")
    for code, color in SEED_COLORS.items():
        LeadStatus.objects.filter(code=code).update(color=color)


def unseed_colors(apps, schema_editor):
    # Field is dropped on reverse, so no data cleanup needed.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("home", "0011_leadstatus"),
    ]

    operations = [
        migrations.AddField(
            model_name="leadstatus",
            name="color",
            field=models.CharField(
                choices=[
                    ("gray", "Gray"), ("blue", "Blue"), ("green", "Green"),
                    ("red", "Red"), ("amber", "Amber"), ("violet", "Violet"),
                    ("orange", "Orange"), ("teal", "Teal"), ("pink", "Pink"),
                ],
                default="gray",
                help_text="Display color used for the status badge throughout the panel.",
                max_length=20,
            ),
        ),
        migrations.RunPython(seed_colors, unseed_colors),
    ]
