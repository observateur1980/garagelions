import csv

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from home.models import State


REQUIRED_COLUMNS = {"code", "name"}
OPTIONAL_COLUMNS = {"is_active"}


def _parse_bool(value, default=True):
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y"}


class Command(BaseCommand):
    help = (
        "Import or upsert State rows from a CSV. "
        "Required columns: " + ", ".join(sorted(REQUIRED_COLUMNS)) + ". "
        "Optional columns: " + ", ".join(sorted(OPTIONAL_COLUMNS)) + ". "
        "Upsert key is `code`."
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

        errors = []
        prepared = []

        for i, row in enumerate(rows, start=2):
            code = (row.get("code") or "").strip().upper()
            name = (row.get("name") or "").strip()

            if not code:
                errors.append(f"row {i}: empty code")
                continue
            if len(code) != 2:
                errors.append(f"row {i} ({code}): code must be exactly 2 letters")
                continue
            if not name:
                errors.append(f"row {i} ({code}): empty name")
                continue

            defaults = {
                "name": name,
                "is_active": _parse_bool(row.get("is_active"), default=True),
            }
            prepared.append((i, code, defaults))

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
            for _, code, defaults in prepared:
                _, was_created = State.objects.update_or_create(
                    code=code, defaults=defaults,
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. Created {created}, updated {updated}, total {len(prepared)}."
        ))
