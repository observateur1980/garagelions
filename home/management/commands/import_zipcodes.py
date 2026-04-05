import csv
from django.core.management.base import BaseCommand
from home.models import SalesPoint, ServiceCity, ZipCode


class Command(BaseCommand):
    help = "Import sales points, cities, and zip codes from CSV"

    def add_arguments(self, parser):
        parser.add_argument("csv_file", type=str)

    def handle(self, *args, **options):
        csv_file = options["csv_file"]

        created_sales_points = 0
        created_cities = 0
        created_zips = 0

        with open(csv_file, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)

            for row in reader:
                sales_point, sp_created = SalesPoint.objects.get_or_create(
                    slug=row["sales_point_slug"].strip(),
                    defaults={
                        "name": row["sales_point_name"].strip(),
                        "is_active": True,
                    },
                )
                if sp_created:
                    created_sales_points += 1

                city, city_created = ServiceCity.objects.get_or_create(
                    sales_point=sales_point,
                    slug=row["city_slug"].strip(),
                    defaults={
                        "name": row["city_name"].strip(),
                        "state": row["state"].strip(),
                        "is_active": True,
                    },
                )
                if city_created:
                    created_cities += 1

                zip_code = row["zip_code"].strip()
                _, zip_created = ZipCode.objects.get_or_create(
                    code=zip_code,
                    defaults={
                        "service_city": city,
                    },
                )
                if zip_created:
                    created_zips += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. SalesPoints: {created_sales_points}, Cities: {created_cities}, ZIPs: {created_zips}"
        ))