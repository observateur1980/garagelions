# models.py
from django.db import models
from multiselectfield import MultiSelectField

from django.utils.text import slugify
from imagekit.models import ImageSpecField
from imagekit.processors import ResizeToFill

from io import BytesIO
from PIL import Image, ImageOps, ImageEnhance
from django.core.files.base import ContentFile

from django.conf import settings
import os


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

            # Convert to RGB (important for PNGs)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            # Crop to square (center)
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
        img = ImageOps.exif_transpose(img)  # fixes rotated iPhone images

        # Convert for JPEG saving
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        elif img.mode == "L":
            img = img.convert("RGB")

        # Exact fit (center-crop) to 550x375
        img = ImageOps.fit(img, (width, height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))

        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        buffer.seek(0)

        # Overwrite same file name (but ensure .jpg extension)
        name = file_field.name
        if not name.lower().endswith((".jpg", ".jpeg")):
            name = name.rsplit(".", 1)[0] + ".jpg"

        file_field.save(name, ContentFile(buffer.read()), save=False)

    except Exception:
        # If anything goes wrong, do not block saving the model
        return


def project_upload_to(instance, filename):
    project = instance if hasattr(instance, "slug") else instance.project
    return f"projects/{project.slug}/{filename}"


class ProjectTag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(unique=True, blank=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Project(models.Model):
    project_name = models.CharField(max_length=200)

    thumbnail_title = models.CharField(
        max_length=120,
        help_text="Short title shown on project thumbnail"
    )

    slug = models.SlugField(unique=True, blank=True)

    tags = models.ManyToManyField(
        ProjectTag,
        blank=True,
        related_name="projects"
    )

    cover_image = models.ImageField(upload_to=project_upload_to)

    order = models.PositiveIntegerField(
        default=0,
        help_text="Manual ordering (lower number = shown first)"
    )

    highlights = models.TextField(
        blank=True,
        help_text="Enter one highlight per line (e.g. COMPLETED 2022 MAY)"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "-created_at"]  # 👈 important

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.project_name)
            slug = base
            i = 1
            while Project.objects.filter(slug=slug).exists():
                i += 1
                slug = f"{base}-{i}"
            self.slug = slug

        cover_changed = True
        if self.pk:
            old = Project.objects.filter(pk=self.pk).only("cover_image").first()
            cover_changed = (not old) or (old.cover_image != self.cover_image)

        super().save(*args, **kwargs)

        if cover_changed and self.cover_image:
            resize_image_to_exact(
                self.cover_image,
                width=550,
                height=375,
                quality=85
            )
            super().save(update_fields=["cover_image"])

    def __str__(self):
        return self.project_name


class BaseProjectImage(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)

    # ORIGINAL image (used for thumbnails – NO watermark)
    image = models.ImageField(upload_to=project_upload_to)

    # WATERMARKED image (used for LightGallery – WITH watermark)
    image_wm = models.ImageField(
        upload_to=project_upload_to,
        blank=True,
        editable=False
    )

    caption = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    # Thumbnail generated from ORIGINAL image
    thumb = ImageSpecField(
        source="image",
        processors=[ResizeToFill(600, 400)],
        format="JPEG",
        options={"quality": 82},
    )

    class Meta:
        abstract = True
        ordering = ["sort_order", "id"]

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)

        # Create watermarked copy ONLY ONCE, without touching original
        if is_new and self.image and not self.image_wm:
            create_watermark(self.image, self.image_wm)
            super().save(update_fields=["image_wm"])


class ProjectBeforeImage(BaseProjectImage):
    pass


class ProjectConstructionImage(BaseProjectImage):
    pass


class ProjectAfterImage(BaseProjectImage):
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

        # Resize watermark relative to image
        wm_width = int(base.width * scale)
        ratio = wm_width / wm.width
        wm_height = int(wm.height * ratio)
        wm = wm.resize((wm_width, wm_height), Image.Resampling.LANCZOS)

        # Opacity
        alpha = wm.split()[3]
        alpha = ImageEnhance.Brightness(alpha).enhance(opacity)
        wm.putalpha(alpha)

        # Bottom-right
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

    # Upload the actual video file (mp4/webm recommended)
    video = models.FileField(upload_to="video_reviews/")

    # Optional: poster image so the video shows a nice preview before play
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
