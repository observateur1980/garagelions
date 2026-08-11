# Sales tax becomes a rate added on top, instead of an amount buried in the
# deal total. Hand-edited from the generated migration so the old column is
# RENAMED rather than dropped — those figures are the only record of what was
# typed under the previous scheme.
from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations, models


def _money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def split_tax_out_of_totals(apps, schema_editor):
    """Restate every priced deal without changing what the customer pays.

    Before: quoted_amount was tax-inclusive and legacy_tax_amount said how much
    of it was tax. After: quoted_amount is the priced work and tax_percent is
    added on top. So the pre-tax price is (quoted - tax), and the rate is that
    tax as a percentage of it.

    The rate rounds to two decimals, which can leave the recomputed tax a few
    cents off the figure originally typed. The customer-facing total is the
    number that must not move, so the pre-tax price absorbs the difference.
    """
    Project = apps.get_model("customlux", "CabinetProject")
    for p in Project.objects.all():
        if p.quoted_amount is None:
            continue  # unpriced — leave blank so it follows the board rate
        old_total = p.quoted_amount
        tax = p.legacy_tax_amount or Decimal("0")
        if tax <= 0:
            # Priced with no tax. Set 0 outright rather than leaving it blank,
            # so raising the board's default rate later can't retroactively
            # add tax to a deal that was agreed without any.
            p.tax_percent = Decimal("0.00")
            p.save(update_fields=["tax_percent"])
            continue
        base = old_total - tax
        pct = (tax / base * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        # Nudge the base so base + round(base * pct) lands back on the total.
        base = (old_total / (1 + pct / 100)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        drift = old_total - (base + _money(base * pct / 100))
        base += drift
        p.quoted_amount = base
        p.tax_percent = pct
        p.save(update_fields=["quoted_amount", "tax_percent"])


def fold_tax_back_into_totals(apps, schema_editor):
    """Reverse: put the tax back inside quoted_amount."""
    Project = apps.get_model("customlux", "CabinetProject")
    for p in Project.objects.all():
        if p.quoted_amount is None:
            continue
        pct = p.tax_percent or Decimal("0")
        tax = _money(p.quoted_amount * pct / 100)
        p.quoted_amount = p.quoted_amount + tax
        p.legacy_tax_amount = tax
        p.save(update_fields=["quoted_amount", "legacy_tax_amount"])


class Migration(migrations.Migration):

    dependencies = [
        ("customlux", "0014_cabinetmember_invite_sent_at_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="cabinetproject",
            old_name="tax_amount",
            new_name="legacy_tax_amount",
        ),
        migrations.AlterField(
            model_name="cabinetproject",
            name="legacy_tax_amount",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=10, null=True
            ),
        ),
        migrations.AddField(
            model_name="cabinetproject",
            name="tax_percent",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=5, null=True,
                verbose_name="Sales tax %",
            ),
        ),
        migrations.AlterField(
            model_name="cabinetproject",
            name="online_fee",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=10, null=True,
                verbose_name="Online transaction fee added to the total",
            ),
        ),
        migrations.AlterField(
            model_name="cabinetsettings",
            name="default_tax_rate",
            field=models.DecimalField(
                decimal_places=2, default=Decimal("0.00"),
                help_text=(
                    "Sales-tax percent applied to any deal that doesn't set "
                    "its own. The tax is added to the deal price; it never "
                    "enters the commission base."
                ),
                max_digits=5,
            ),
        ),
        migrations.RunPython(split_tax_out_of_totals, fold_tax_back_into_totals),
    ]
