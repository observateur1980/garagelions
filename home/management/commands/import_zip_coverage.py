import csv

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from home.models import State, Region, SalesPoint, ZipCoverage


REQUIRED_COLUMNS = {
    "zip_code", "state_code", "region_code", "sales_point_code", "coverage_type",
}
OPTIONAL_COLUMNS = {
    "city", "county", "backup_sales_point_code", "drive_time_target",
    "is_active", "notes",
}
VALID_COVERAGE = {c for c, _ in ZipCoverage.COVERAGE_CHOICES}


def _parse_bool(value, default=True):
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y"}


class Command(BaseCommand):
    help = (
        "Import or upsert ZIP coverage rows from a CSV. "
        "Required columns: " + ", ".join(sorted(REQUIRED_COLUMNS)) + ". "
        "Optional columns: " + ", ".join(sorted(OPTIONAL_COLUMNS)) + ". "
        "ZIP is the upsert key; FKs must already exist."
    )

    def add_arguments(self, parser):
        parser.add_argument("csv_file", type=str)
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Validate the CSV and report changes without writing.",
        )

    def handle(self, *args, **options):
        path = options["csv_file"]
        dry = options["dry_run"]

        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
            if missing:
                raise CommandError(f"CSV missing required columns: {sorted(missing)}")
            rows = list(reader)

        # Cache lookups so a 10k-row CSV doesn't issue 30k queries.
        states = {s.code: s for s in State.objects.all()}
        regions = {(r.state.code, r.code): r for r in Region.objects.select_related("state")}
        sps_by_region = {
            (sp.region.state.code if sp.region_id else None, sp.region.code if sp.region_id else None, sp.code): sp
            for sp in SalesPoint.objects.select_related("region__state").exclude(code="")
        }

        errors = []
        to_upsert = []  # list of (row_no, defaults_dict, lookup_dict)

        for i, row in enumerate(rows, start=2):  # start=2 to account for header line
            zip_code = (row.get("zip_code") or "").strip()
            state_code = (row.get("state_code") or "").strip().upper()
            region_code = (row.get("region_code") or "").strip().upper()
            sp_code = (row.get("sales_point_code") or "").strip().upper()
            backup_code = (row.get("backup_sales_point_code") or "").strip().upper()
            coverage = (row.get("coverage_type") or "").strip().lower() or ZipCoverage.CORE

            if not zip_code:
                errors.append(f"row {i}: empty zip_code")
                continue

            state = states.get(state_code)
            if not state:
                errors.append(f"row {i} ({zip_code}): unknown state_code '{state_code}'")
                continue

            region = regions.get((state_code, region_code))
            if not region:
                errors.append(f"row {i} ({zip_code}): unknown region_code '{region_code}' for state '{state_code}'")
                continue

            sp = sps_by_region.get((state_code, region_code, sp_code))
            if not sp:
                errors.append(f"row {i} ({zip_code}): unknown sales_point_code '{sp_code}' for region '{state_code}-{region_code}'")
                continue

            backup = None
            if backup_code:
                backup = sps_by_region.get((state_code, region_code, backup_code))
                if not backup:
                    errors.append(f"row {i} ({zip_code}): unknown backup_sales_point_code '{backup_code}'")
                    continue

            if coverage not in VALID_COVERAGE:
                errors.append(f"row {i} ({zip_code}): invalid coverage_type '{coverage}'")
                continue

            drive = (row.get("drive_time_target") or "").strip()
            try:
                drive_int = int(drive) if drive else None
            except ValueError:
                errors.append(f"row {i} ({zip_code}): drive_time_target '{drive}' is not an integer")
                continue

            defaults = {
                "city": (row.get("city") or "").strip(),
                "county": (row.get("county") or "").strip(),
                "state": state,
                "region": region,
                "sales_point": sp,
                "backup_sales_point": backup,
                "coverage_type": coverage,
                "drive_time_target": drive_int,
                "is_active": _parse_bool(row.get("is_active"), default=True),
                "notes": (row.get("notes") or "").strip(),
            }
            to_upsert.append((i, zip_code, defaults))

        if errors:
            self.stderr.write(self.style.ERROR(f"Found {len(errors)} error(s):"))
            for msg in errors:
                self.stderr.write(f"  - {msg}")
            raise CommandError("Aborting — fix the rows above and re-run.")

        if dry:
            self.stdout.write(self.style.WARNING(
                f"Dry run: {len(to_upsert)} row(s) would be upserted. No changes written."
            ))
            return

        created = 0
        updated = 0
        with transaction.atomic():
            for _, zip_code, defaults in to_upsert:
                _, was_created = ZipCoverage.objects.update_or_create(
                    zip_code=zip_code, defaults=defaults,
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. Created {created}, updated {updated}, total {len(to_upsert)}."
        ))
