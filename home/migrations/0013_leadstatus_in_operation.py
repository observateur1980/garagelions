from django.db import migrations


IN_OPERATION = {
    "code": "in_operation",
    "label": "In Operation",
    "order": 15,
    "color": "teal",
    "is_protected": True,
}


def seed_in_operation(apps, schema_editor):
    LeadStatus = apps.get_model("home", "LeadStatus")
    LeadStatus.objects.update_or_create(
        code=IN_OPERATION["code"],
        defaults={
            "label": IN_OPERATION["label"],
            "order": IN_OPERATION["order"],
            "color": IN_OPERATION["color"],
            "is_protected": IN_OPERATION["is_protected"],
        },
    )


def unseed_in_operation(apps, schema_editor):
    LeadStatus = apps.get_model("home", "LeadStatus")
    LeadStatus.objects.filter(code=IN_OPERATION["code"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("home", "0012_leadstatus_color"),
    ]

    operations = [
        migrations.RunPython(seed_in_operation, unseed_in_operation),
    ]
