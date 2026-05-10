import csv
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from home.models import State, Region, SalesPoint


REQUIRED_COLUMNS = {"name", "state_code", "region_code", "code"}
OPTIONAL_COLUMNS = {
    "slug", "base_city", "location_type",
    "is_active", "is_featured", "order",
    "address_line_1", "address_line_2",
    "local_phone", "local_email",
    "lead_notification_email", "from_email", "reply_to_email",
    "assigned_salesperson",
    "latitude", "longitude", "royalty_rate",
}
VALID_LOCATION_TYPES = {"company", "franchise", "rental"}


def _parse_bool(value, default=True):
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y"}


def _parse_decimal(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValueError(value)


def _parse_int(value):
    if value is None or str(value).strip() == "":
        return None
    return int(str(value).strip())


class Command(BaseCommand):
    help = (
        "Import or upsert SalesPoint rows from a CSV. "
        "Required columns: " + ", ".join(sorted(REQUIRED_COLUMNS)) + ". "
        "Optional columns: " + ", ".join(sorted(OPTIONAL_COLUMNS)) + ". "
        "Upsert key is (region, code); state/region FKs must already exist."
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

        states = {s.code: s for s in State.objects.all()}
        regions = {(r.state.code, r.code): r for r in Region.objects.select_related("state")}

        errors = []
        prepared = []  # list of (row_no, region, code, defaults)

        for i, row in enumerate(rows, start=2):
            name = (row.get("name") or "").strip()
            state_code = (row.get("state_code") or "").strip().upper()
            region_code = (row.get("region_code") or "").strip().upper()
            code = (row.get("code") or "").strip().upper()

            if not name:
                errors.append(f"row {i}: empty name")
                continue
            if not code:
                errors.append(f"row {i} ({name}): empty sales-point code")
                continue

            state = states.get(state_code)
            if not state:
                errors.append(f"row {i} ({name}): unknown state_code '{state_code}'")
                continue

            region = regions.get((state_code, region_code))
            if not region:
                errors.append(
                    f"row {i} ({name}): unknown region_code '{region_code}' for state '{state_code}'"
                )
                continue

            location_type = (row.get("location_type") or "").strip().lower() or "company"
            if location_type not in VALID_LOCATION_TYPES:
                errors.append(f"row {i} ({name}): invalid location_type '{location_type}'")
                continue

            try:
                lat = _parse_decimal(row.get("latitude"))
                lng = _parse_decimal(row.get("longitude"))
                royalty = _parse_decimal(row.get("royalty_rate"))
            except ValueError as bad:
                errors.append(f"row {i} ({name}): non-numeric decimal '{bad}'")
                continue

            try:
                order = _parse_int(row.get("order"))
            except ValueError:
                errors.append(f"row {i} ({name}): order must be an integer")
                continue

            defaults = {
                "name": name,
                "region": region,
                "base_city": (row.get("base_city") or "").strip(),
                "location_type": location_type,
                "is_active": _parse_bool(row.get("is_active"), default=True),
                "is_featured": _parse_bool(row.get("is_featured"), default=False),
                "address_line_1": (row.get("address_line_1") or "").strip(),
                "address_line_2": (row.get("address_line_2") or "").strip(),
                "local_phone": (row.get("local_phone") or "").strip(),
                "local_email": (row.get("local_email") or "").strip(),
                "lead_notification_email": (row.get("lead_notification_email") or "").strip(),
                "from_email": (row.get("from_email") or "").strip(),
                "reply_to_email": (row.get("reply_to_email") or "").strip(),
                "assigned_salesperson": (row.get("assigned_salesperson") or "").strip(),
            }
            slug = (row.get("slug") or "").strip().lower()
            if slug:
                defaults["slug"] = slug
            if order is not None:
                defaults["order"] = order
            if lat is not None:
                defaults["latitude"] = lat
            if lng is not None:
                defaults["longitude"] = lng
            if royalty is not None:
                defaults["royalty_rate"] = royalty

            prepared.append((i, region, code, defaults))

        if errors:
            self.stderr.write(self.style.ERROR(f"Found {len(errors)} error(s):"))
            for msg in errors:
                self.stderr.write(f"  - {msg}")
            raise CommandError("Aborting — fix the rows above and re-run.")

        if dry:
            self.stdout.write(self.style.WARNING(
                f"Dry run: {len(prepared)} row(s) would be upserted. No changes written."
            ))
            return

        created = 0
        updated = 0
        with transaction.atomic():
            for _, region, code, defaults in prepared:
                obj, was_created = SalesPoint.objects.update_or_create(
                    region=region, code=code, defaults=defaults,
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. Created {created}, updated {updated}, total {len(prepared)}."
        ))
