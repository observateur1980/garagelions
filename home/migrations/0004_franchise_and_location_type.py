# home/migrations/0004_salespoint_location_type_franchiseagreement_fix_slug.py
# Run: python manage.py makemigrations home --name franchise_and_location_type
# Then: python manage.py migrate
#
# OR paste this file directly into home/migrations/ and run: python manage.py migrate

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("home", "0003_remove_leadmodel_name_leadmodel_first_name_and_more"),
    ]

    operations = [
        # 1. Add location_type to SalesPoint
        migrations.AddField(
            model_name="salespoint",
            name="location_type",
            field=models.CharField(
                choices=[
                    ("company", "Company-Owned"),
                    ("franchise", "Franchise"),
                    ("rental", "Rental / Licensed"),
                ],
                default="company",
                max_length=20,
            ),
        ),
        # 2. Add royalty_rate to SalesPoint
        migrations.AddField(
            model_name="salespoint",
            name="royalty_rate",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Royalty percentage (e.g. 6.00 for 6%)",
                max_digits=5,
                null=True,
            ),
        ),
        # 3. Fix ServiceCity slug — remove global unique, add scoped constraint
        migrations.AlterField(
            model_name="servicecity",
            name="slug",
            field=models.SlugField(blank=True, max_length=120),
        ),
        migrations.AddConstraint(
            model_name="servicecity",
            constraint=models.UniqueConstraint(
                fields=["sales_point", "slug"],
                name="unique_salespoint_city_slug",
            ),
        ),
        # 4. Create FranchiseAgreement
        migrations.CreateModel(
            name="FranchiseAgreement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("franchisee_legal_name", models.CharField(max_length=200)),
                ("franchisee_contact_name", models.CharField(blank=True, max_length=120)),
                ("franchisee_email", models.EmailField(blank=True)),
                ("franchisee_phone", models.CharField(blank=True, max_length=30)),
                ("upfront_fee", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, help_text="One-time franchise fee in USD")),
                ("royalty_rate", models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, help_text="Monthly royalty as a percentage of gross revenue")),
                ("marketing_fee_rate", models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, help_text="Marketing fund contribution as % of gross revenue")),
                ("territory_notes", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("active", "Active"), ("expired", "Expired"), ("terminated", "Terminated")], default="pending", max_length=20)),
                ("agreement_date", models.DateField(blank=True, null=True)),
                ("start_date", models.DateField(blank=True, null=True)),
                ("expiry_date", models.DateField(blank=True, null=True)),
                ("renewal_date", models.DateField(blank=True, null=True)),
                ("agreement_document", models.FileField(blank=True, null=True, upload_to="franchise/agreements/")),
                ("internal_notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("sales_point", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="franchise_agreement",
                    to="home.salespoint",
                )),
            ],
            options={
                "verbose_name": "Franchise Agreement",
                "verbose_name_plural": "Franchise Agreements",
                "ordering": ["-created_at"],
            },
        ),
    ]