"""Seed the default cabinets workflow.

Stages are admin-editable afterwards — this only fills an empty board so the
first lead you send has somewhere to land. Reversing the migration removes
only the stages that still have no projects attached.
"""
from django.db import migrations

STAGES = [
    ("new",        "New",            "#6b7280", 10, False, False),
    ("measure",    "Measure",        "#2563eb", 20, False, False),
    ("design",     "Design",         "#7c3aed", 30, False, False),
    ("quoted",     "Quoted",         "#c9a227", 40, False, False),
    ("approved",   "Approved",       "#0891b2", 50, False, False),
    ("ordered",    "Ordered",        "#ea580c", 60, False, False),
    ("production", "In Production",  "#db2777", 70, False, False),
    ("install",    "Install",        "#059669", 80, False, False),
    ("complete",   "Complete",       "#065f46", 90, True,  False),
    ("cancelled",  "Cancelled",      "#991b1b", 100, False, True),
]


def seed(apps, schema_editor):
    CabinetStage = apps.get_model("customlux", "CabinetStage")
    for code, label, color, order, is_won, is_lost in STAGES:
        CabinetStage.objects.get_or_create(
            code=code,
            defaults={
                "label": label, "color": color, "order": order,
                "is_won": is_won, "is_lost": is_lost, "is_active": True,
            },
        )


def unseed(apps, schema_editor):
    CabinetStage = apps.get_model("customlux", "CabinetStage")
    CabinetStage.objects.filter(
        code__in=[s[0] for s in STAGES], projects__isnull=True
    ).delete()


class Migration(migrations.Migration):

    dependencies = [("customlux", "0001_initial")]

    operations = [migrations.RunPython(seed, unseed)]
