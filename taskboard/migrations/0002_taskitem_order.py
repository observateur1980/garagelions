from django.db import migrations, models


def backfill_order(apps, schema_editor):
    TaskItem = apps.get_model("taskboard", "TaskItem")
    for idx, task in enumerate(TaskItem.objects.order_by("-created_at")):
        task.order = idx
        task.save(update_fields=["order"])


class Migration(migrations.Migration):

    dependencies = [
        ("taskboard", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="taskitem",
            name="order",
            field=models.IntegerField(default=0, db_index=True),
        ),
        migrations.AlterModelOptions(
            name="taskitem",
            options={"ordering": ["order", "-created_at"]},
        ),
        migrations.RunPython(backfill_order, reverse_code=migrations.RunPython.noop),
    ]
