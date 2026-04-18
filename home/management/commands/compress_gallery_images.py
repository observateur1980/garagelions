"""
Management command to compress existing gallery images.

Resizes images to max 1920px on longest side, re-applies watermark,
and saves at 85% JPEG quality.

Usage:
    python manage.py compress_gallery_images          # dry-run (show what would change)
    python manage.py compress_gallery_images --apply   # actually compress
"""
from django.core.management.base import BaseCommand
from home.models import GalleryItem, apply_watermark_to_field
from PIL import Image, ImageOps
from io import BytesIO
from django.core.files.base import ContentFile
import os


class Command(BaseCommand):
    help = "Compress existing gallery images (resize to max 1920px, quality 85)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually compress images. Without this flag, only shows what would change.",
        )
        parser.add_argument(
            "--max-dimension",
            type=int,
            default=1920,
            help="Max width/height in pixels (default: 1920)",
        )
        parser.add_argument(
            "--quality",
            type=int,
            default=85,
            help="JPEG quality 1-100 (default: 85)",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        max_dim = options["max_dimension"]
        quality = options["quality"]

        items = GalleryItem.objects.filter(media_type=GalleryItem.IMAGE)
        self.stdout.write(f"Found {items.count()} gallery images to check.\n")

        compressed = 0
        skipped = 0
        total_saved = 0

        for item in items:
            if not item.file:
                skipped += 1
                continue

            try:
                item.file.open("rb")
                old_size = item.file.size
                img = Image.open(item.file)
                img = ImageOps.exif_transpose(img)
                w, h = img.size
                item.file.close()
            except Exception as e:
                self.stderr.write(f"  SKIP {item.file.name}: {e}")
                skipped += 1
                continue

            needs_resize = max(w, h) > max_dim

            if not needs_resize and old_size < 300_000:
                skipped += 1
                continue

            if not apply:
                self.stdout.write(
                    f"  WOULD compress: {item.file.name}  "
                    f"{w}x{h}  {old_size / 1024:.0f}KB"
                )
                compressed += 1
                continue

            # Compress: resize + re-save at target quality (no re-watermark)
            try:
                item.file.open("rb")
                img = Image.open(item.file)
                img = ImageOps.exif_transpose(img)
                if img.mode != "RGB":
                    img = img.convert("RGB")
                item.file.close()

                if needs_resize:
                    img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

                buf = BytesIO()
                fname = os.path.basename(item.file.name)
                if not fname.lower().endswith((".jpg", ".jpeg")):
                    fname = fname.rsplit(".", 1)[0] + ".jpg"
                img.save(buf, format="JPEG", quality=quality, optimize=True)
                new_size = buf.tell()
                buf.seek(0)

                saved_kb = (old_size - new_size) / 1024
                if new_size >= old_size:
                    self.stdout.write(
                        f"  SKIP (already small): {item.file.name}"
                    )
                    skipped += 1
                    continue

                item.file.save(fname, ContentFile(buf.read()), save=False)
                # Update dimensions
                item.width, item.height = img.size
                GalleryItem.objects.filter(pk=item.pk).update(
                    file=item.file.name,
                    width=item.width,
                    height=item.height,
                )

                total_saved += old_size - new_size
                compressed += 1
                self.stdout.write(
                    f"  OK {item.file.name}: "
                    f"{old_size / 1024:.0f}KB -> {new_size / 1024:.0f}KB  "
                    f"(saved {saved_kb:.0f}KB)"
                )
            except Exception as e:
                self.stderr.write(f"  ERROR {item.file.name}: {e}")
                skipped += 1

        self.stdout.write(
            f"\nDone. Compressed: {compressed}, Skipped: {skipped}, "
            f"Total saved: {total_saved / 1024 / 1024:.1f}MB"
        )
        if not apply and compressed:
            self.stdout.write(
                "\nThis was a dry run. Add --apply to actually compress."
            )
