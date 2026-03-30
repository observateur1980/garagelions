# models.py
from django.db import models
from django.core.validators import FileExtensionValidator
from multiselectfield import MultiSelectField

from django.utils.text import slugify
from imagekit.models import ImageSpecField
from imagekit.processors import ResizeToFill

from io import BytesIO
from PIL import Image, ImageOps, ImageEnhance
from django.core.files.base import ContentFile

from django.conf import settings
import os
from pathlib import Path


class Testimonial(models.Model):
    name = models.CharField(max_length=100)
    photo = models.ImageField(upload_to="testimonials/")
    rating = models.PositiveSmallIntegerField(default=5)
    message = models.TextField()
    source_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.order} - {self.name}"

    @property
    def filled_stars(self):
        return range(self.rating)

    @property
    def empty_stars(self):
        return range(5 - self.rating)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        if self.photo:
            img = Image.open(self.photo.path)

            TARGET_SIZE = (200, 200)

            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            width, height = img.size
            min_side = min(width, height)

            left = (width - min_side) / 2
            top = (height - min_side) / 2
            right = (width + min_side) / 2
            bottom = (height + min_side) / 2

            img = img.crop((left, top, right, bottom))
            img = img.resize(TARGET_SIZE, Image.LANCZOS)

            img.save(self.photo.path, optimize=True, quality=85)


def resize_image_to_exact(file_field, width=550, height=375, quality=85):
    """
    Resize the uploaded image file to an exact size (cropping if needed) and
    overwrite the same ImageField file.
    """
    if not file_field:
        return

    try:
        img = Image.open(file_field)
        img = ImageOps.exif_transpose(img)

        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        elif img.mode == "L":
            img = img.convert("RGB")

        img = ImageOps.fit(
            img,
            (width, height),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5)
        )

        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        buffer.seek(0)

        name = file_field.name
        if not name.lower().endswith((".jpg", ".jpeg")):
            name = name.rsplit(".", 1)[0] + ".jpg"

        file_field.save(name, ContentFile(buffer.read()), save=False)

    except Exception:
        return


def gallery_cover_upload_to(instance, filename):
    slug = instance.slug or slugify(instance.name) or "gallery"
    return f"galleries/{slug}/covers/{filename}"


def gallery_media_upload_to(instance, filename):
    gallery = getattr(instance, "gallery", None)
    slug = gallery.slug or slugify(gallery.name) if gallery else "gallery"
    return f"galleries/{slug}/items/{filename}"


def gallery_thumb_upload_to(instance, filename):
    gallery = getattr(instance, "gallery", None)
    slug = gallery.slug or slugify(gallery.name) if gallery else "gallery"
    return f"galleries/{slug}/thumbnails/{filename}"


class Gallery(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True)
    thumbnail = models.ImageField(
        upload_to=gallery_cover_upload_to,
        blank=True,
        null=True,
        help_text="Optional gallery cover image used on the galleries page."
    )
    page_title = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional custom title for the gallery detail page."
    )
    intro_text = models.TextField(
        blank=True,
        help_text="Optional intro text shown near the top of the gallery detail page."
    )
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "name"]
        verbose_name_plural = "Galleries"

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)
            slug = base
            i = 1
            while Gallery.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                i += 1
                slug = f"{base}-{i}"
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @property
    def cover_image(self):
        if self.thumbnail:
            return self.thumbnail
        first_item = self.items.order_by("sort_order", "id").first()
        return first_item.effective_thumbnail if first_item else None


class GalleryItem(models.Model):
    IMAGE = "image"
    VIDEO = "video"
    MEDIA_TYPE_CHOICES = [
        (IMAGE, "Photo"),
        (VIDEO, "Video"),
    ]

    gallery = models.ForeignKey(
        Gallery,
        on_delete=models.CASCADE,
        related_name="items"
    )
    title = models.CharField(max_length=200, blank=True)
    section_heading = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional heading shown before this photo or video."
    )
    text_before = models.TextField(
        blank=True,
        help_text="Optional text shown before this photo or video."
    )
    text_after = models.TextField(
        blank=True,
        help_text="Optional text shown after this photo or video."
    )
    media_type = models.CharField(max_length=10, choices=MEDIA_TYPE_CHOICES, default=IMAGE)
    file = models.FileField(
        upload_to=gallery_media_upload_to,
        validators=[FileExtensionValidator(allowed_extensions=[
            "jpg", "jpeg", "png", "webp", "gif",
            "mp4", "mov", "m4v", "webm", "ogg"
        ])]
    )
    thumbnail = models.ImageField(
        upload_to=gallery_thumb_upload_to,
        blank=True,
        null=True,
        help_text="Required for videos. Optional for photos."
    )
    width = models.PositiveIntegerField(blank=True, null=True, editable=False)
    height = models.PositiveIntegerField(blank=True, null=True, editable=False)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        label = self.title or Path(self.file.name).name
        return f"{self.gallery.name} - {label}"

    @property
    def effective_thumbnail(self):
        if self.thumbnail:
            return self.thumbnail
        if self.media_type == self.IMAGE:
            return self.file
        return None

    @property
    def is_square(self):
        if self.width and self.height:
            ratio = self.width / self.height
            return 0.9 <= ratio <= 1.1
        return False

    @property
    def layout_class(self):
        return "is-square" if self.is_square else "is-wide"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        source = self.thumbnail if self.thumbnail else (self.file if self.media_type == self.IMAGE else None)
        if source:
            try:
                source.open("rb")
                img = Image.open(source)
                img = ImageOps.exif_transpose(img)
                self.width, self.height = img.size
                source.close()
                GalleryItem.objects.filter(pk=self.pk).update(width=self.width, height=self.height)
            except Exception:
                pass


class LeadModel(models.Model):
    class Meta:
        verbose_name = "Lead"
        verbose_name_plural = "Leads"

    CONSULTATION_CHOICES = [
        ('kitchen', 'Kitchen Remodeling'),
        ('bathroom', 'Bathroom Remodeling'),
        ('garage', 'Garage Remodeling'),
        ('fullhouse', 'Full House Remodeling'),
        ('newconstruction', 'New Construction'),
        ('adu', 'ADU'),
    ]

    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    consultation_types = MultiSelectField(choices=CONSULTATION_CHOICES, blank=True)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Lead Request #{self.id} from {self.name}"


class LeadAttachment(models.Model):
    """Optional photos/videos uploaded by the customer with the consultation request."""

    lead = models.ForeignKey(
        LeadModel,
        related_name="attachments",
        on_delete=models.CASCADE,
    )

    file = models.FileField(upload_to="lead_attachments/%Y/%m/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at", "-id"]

    def __str__(self):
        return f"Lead #{self.lead_id} - {self.file.name}"


def create_watermark(source_field, target_field, opacity=0.25, scale=0.25, margin=20):
    """
    Create a watermarked copy WITHOUT touching the original image.
    """
    if not source_field:
        return

    try:
        base = Image.open(source_field).convert("RGBA")

        watermark_path = os.path.join(
            settings.BASE_DIR, "static", "images", "watermark.png"
        )
        if not os.path.exists(watermark_path):
            return

        wm = Image.open(watermark_path).convert("RGBA")

        wm_width = int(base.width * scale)
        ratio = wm_width / wm.width
        wm_height = int(wm.height * ratio)
        wm = wm.resize((wm_width, wm_height), Image.Resampling.LANCZOS)

        alpha = wm.split()[3]
        alpha = ImageEnhance.Brightness(alpha).enhance(opacity)
        wm.putalpha(alpha)

        x = base.width - wm.width - margin
        y = base.height - wm.height - margin
        base.alpha_composite(wm, (x, y))

        base = base.convert("RGB")

        buffer = BytesIO()
        base.save(buffer, format="JPEG", quality=85, optimize=True)
        buffer.seek(0)

        name = source_field.name.rsplit(".", 1)[0] + "_wm.jpg"
        target_field.save(name, ContentFile(buffer.read()), save=False)

    except Exception:
        return


class VideoReview(models.Model):
    title = models.CharField(max_length=200)
    customer_name = models.CharField(max_length=100, blank=True)

    video = models.FileField(upload_to="video_reviews/")

    thumbnail = models.ImageField(
        upload_to="video_reviews/thumbnails/",
        blank=True,
        null=True
    )

    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "-created_at"]

    def __str__(self):
        return f"{self.order} - {self.title}"