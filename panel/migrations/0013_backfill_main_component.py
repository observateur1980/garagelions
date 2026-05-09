from django.db import migrations


def backfill_main_component(apps, schema_editor):
    Estimate = apps.get_model("panel", "Estimate")
    EstimateComponent = apps.get_model("panel", "EstimateComponent")
    EstimateItem = apps.get_model("panel", "EstimateItem")

    for est in Estimate.objects.all():
        comp = est.components.order_by("order", "id").first()
        if comp is None:
            comp = EstimateComponent.objects.create(estimate=est, name="Main", order=0)
        EstimateItem.objects.filter(estimate=est, component__isnull=True).update(component=comp)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("panel", "0012_estimatecomponent_estimateitem_component"),
    ]

    operations = [
        migrations.RunPython(backfill_main_component, noop_reverse),
    ]
