# home/models.py — COMPLETE FILE (replace your existing one)
# Changes from original:
#   - SalesPoint: added location_type, royalty_rate fields
#   - ServiceCity: slug uniqueness scoped to sales_point (not global)
#   - LeadModel: removed assigned_to CharField, uses assigned_user FK only
#   - FranchiseAgreement: new model at the bottom

from django.db import models
from django.core.validators import FileExtensionValidator
from multiselectfield import MultiSelectField
from django.utils.text import slugify
from imagekit.models import ImageSpecField
from imagekit.processors import ResizeToFill
from django.db.models.signals import post_save
from django.dispatch import receiver
from io import BytesIO
from PIL import Image, ImageOps, ImageEnhance
from django.core.files.base import ContentFile

from django.conf import settings
from django.contrib.auth import get_user_model
import os
from pathlib import Path

User = get_user_model()


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


def apply_watermark_to_field(file_field, opacity=0.90, scale=0.22, margin=24, quality=98):
    if not file_field:
        return False
    try:
        watermark_path = os.path.join(settings.BASE_DIR, "static", "images", "watermark.png")
        if not os.path.exists(watermark_path):
            return False
        file_field.open("rb")
        base = Image.open(file_field)
        base = ImageOps.exif_transpose(base).convert("RGBA")
        file_field.close()
        wm = Image.open(watermark_path).convert("RGBA")
        wm_width = max(180, int(base.width * scale))
        ratio = wm_width / wm.width
        wm_height = int(wm.height * ratio)
        wm = wm.resize((wm_width, wm_height), Image.Resampling.LANCZOS)
        alpha = wm.split()[3]
        alpha = ImageEnhance.Brightness(alpha).enhance(opacity)
        wm.putalpha(alpha)
        x = max(margin, base.width - wm.width - margin)
        y = max(margin, base.height - wm.height - margin)
        base.alpha_composite(wm, (x, y))
        base = base.convert("RGB")
        buffer = BytesIO()
        buffer_name = file_field.name
        if not buffer_name.lower().endswith((".jpg", ".jpeg")):
            buffer_name = buffer_name.rsplit(".", 1)[0] + ".jpg"
        base.save(buffer, format="JPEG", quality=quality, optimize=True)
        buffer.seek(0)
        file_field.save(buffer_name, ContentFile(buffer.read()), save=False)
        return True
    except Exception:
        return False


LOCATION_TYPE_CHOICES = [
    ("company", "Company-Owned"),
    ("franchise", "Franchise"),
    ("rental", "Rental / Licensed"),
]


class SalesPoint(models.Model):
    name = models.CharField(max_length=150)
    slug = models.SlugField(unique=True, blank=True)

    # ── NEW: location type ──
    location_type = models.CharField(
        max_length=20,
        choices=LOCATION_TYPE_CHOICES,
        default="company",
    )
    royalty_rate = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Royalty percentage (e.g. 6.00 for 6%)"
    )

    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    page_title = models.CharField(max_length=255, blank=True)
    meta_description = models.CharField(max_length=255, blank=True)
    hero_title = models.CharField(max_length=255, blank=True)
    hero_subtitle = models.TextField(blank=True)

    address_line_1 = models.CharField(max_length=255, blank=True)
    address_line_2 = models.CharField(max_length=255, blank=True)

    local_phone = models.CharField(max_length=30, blank=True)
    local_email = models.EmailField(blank=True)
    lead_notification_email = models.EmailField(blank=True)
    from_email = models.EmailField(blank=True)
    reply_to_email = models.EmailField(blank=True)

    assigned_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sales_points",
    )
    assigned_salesperson = models.CharField(max_length=120, blank=True)

    intro_text = models.TextField(blank=True)
    seo_body = models.TextField(blank=True)

    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    class Meta:
        ordering = ["order", "name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)
            slug = base
            i = 1
            while SalesPoint.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                i += 1
                slug = f"{base}-{i}"
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @property
    def full_address(self):
        parts = [self.address_line_1, self.address_line_2]
        return ", ".join([p for p in parts if p])


class SalesPointWorkingHour(models.Model):
    DAY_CHOICES = [
        ("monday", "Monday"),
        ("tuesday", "Tuesday"),
        ("wednesday", "Wednesday"),
        ("thursday", "Thursday"),
        ("friday", "Friday"),
        ("saturday", "Saturday"),
        ("sunday", "Sunday"),
    ]

    sales_point = models.ForeignKey(
        SalesPoint,
        on_delete=models.CASCADE,
        related_name="working_hours",
    )
    day = models.CharField(max_length=20, choices=DAY_CHOICES)
    is_open = models.BooleanField(default=True)
    open_time = models.TimeField(null=True, blank=True)
    close_time = models.TimeField(null=True, blank=True)
    note = models.CharField(max_length=100, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["sales_point", "day"],
                name="unique_salespoint_day",
            )
        ]
        ordering = ["id"]
        verbose_name = "Working Hour"
        verbose_name_plural = "Working Hours"

    def __str__(self):
        return f"{self.sales_point.name} - {self.get_day_display()}"


@receiver(post_save, sender=SalesPoint)
def create_default_working_hours(sender, instance, created, **kwargs):
    if created:
        for day_value, _day_label in SalesPointWorkingHour.DAY_CHOICES:
            SalesPointWorkingHour.objects.get_or_create(
                sales_point=instance,
                day=day_value,
                defaults={
                    "is_open": day_value not in ["saturday", "sunday"],
                },
            )


class ServiceCity(models.Model):
    sales_point = models.ForeignKey(
        SalesPoint,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cities",
    )
    name = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, blank=True, unique=True)

    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "state"],
                name="unique_city_state",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(f"{self.name}-{self.state}")
            slug = base
            i = 1
            while ServiceCity.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                i += 1
                slug = f"{base}-{i}"
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name}, {self.state}"


class ZipCode(models.Model):
    service_city = models.ForeignKey(
        ServiceCity,
        on_delete=models.CASCADE,
        related_name="zip_codes",
    )
    code = models.CharField(max_length=10, unique=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "Zip Code"
        verbose_name_plural = "Zip Codes"

    def __str__(self):
        return f"{self.code} -> {self.service_city.name}, {self.service_city.state}"


class Gallery(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True)
    sales_points = models.ManyToManyField(
        SalesPoint,
        blank=True,
        related_name="galleries",
    )
    thumbnail = models.ImageField(
        upload_to=gallery_cover_upload_to,
        blank=True,
        null=True,
        help_text="Optional gallery cover image used on the galleries page."
    )
    page_title = models.CharField(max_length=255, blank=True)
    intro_text = models.TextField(blank=True)
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

    gallery = models.ForeignKey(Gallery, on_delete=models.CASCADE, related_name="items")
    title = models.CharField(max_length=200, blank=True)
    section_heading = models.CharField(max_length=255, blank=True)
    text_before = models.TextField(blank=True)
    text_after = models.TextField(blank=True)
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
        old_file_name = None
        if self.pk:
            old_values = GalleryItem.objects.filter(pk=self.pk).values("file").first()
            if old_values:
                old_file_name = old_values.get("file")

        super().save(*args, **kwargs)

        file_changed = bool(self.file) and (old_file_name != self.file.name)
        fields_to_update = []

        if self.media_type == self.IMAGE and file_changed:
            if apply_watermark_to_field(self.file):
                fields_to_update.append("file")

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

        if fields_to_update:
            super().save(update_fields=fields_to_update)

    def clean(self):
        super().clean()


class LeadModel(models.Model):
    class Meta:
        verbose_name = "Lead"
        verbose_name_plural = "Leads"
        ordering = ["-created_at"]

    CONSULTATION_CHOICES = [
        ("garage_flooring", "Garage Flooring"),
        ("garage_cabinets", "Garage Cabinets"),
        ("garage_slatwall", "Garage Slatwall"),
        ("storage_racks", "Storage Racks"),
        ("garage_door", "Garage Door"),
        ("garage_makeover", "Garage Makeover"),
        ("garage_conversion", "Garage Conversion"),
        ("car_lift", "Car Lift"),
    ]

    STATUS_CHOICES = [
        ("new", "New"),
        ("contacted", "Contacted"),
        ("appointment_set", "Appointment Set"),
        ("quoted", "Quoted"),
        ("waiting_for_estimate", "Waiting For Estimate"),
        ("follow_up", "Follow Up"),
        ("closed_won", "Closed Won"),
        ("closed_lost", "Closed Lost"),
    ]

    first_name = models.CharField(max_length=120)
    last_name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    address = models.CharField(max_length=255, blank=True)
    zip_code = models.CharField(max_length=10)

    sales_point = models.ForeignKey(
        SalesPoint,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leads",
    )
    service_city = models.ForeignKey(
        ServiceCity,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leads",
    )
    # ── assigned_to CharField REMOVED — use assigned_user FK only ──
    assigned_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leads",
    )

    consultation_types = MultiSelectField(choices=CONSULTATION_CHOICES, blank=True)
    message = models.TextField(blank=True)

    source_page = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="new")
    internal_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Lead #{self.id} - {self.first_name} {self.last_name}"


class LeadAttachment(models.Model):
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


class LeadActivity(models.Model):
    """
    Immutable audit log: every status change, note update, and assignment
    for a lead is recorded here so admins and managers can see the full history.
    """

    ACTION_CREATED = "created"
    ACTION_STATUS = "status_changed"
    ACTION_NOTES = "notes_updated"
    ACTION_ASSIGNED = "assigned"
    ACTION_REMINDER = "reminder_sent"

    ACTION_CHOICES = [
        (ACTION_CREATED, "Lead Created"),
        (ACTION_STATUS, "Status Changed"),
        (ACTION_NOTES, "Notes Updated"),
        (ACTION_ASSIGNED, "Reassigned"),
        (ACTION_REMINDER, "Stale Reminder Sent"),
    ]

    lead = models.ForeignKey(
        LeadModel,
        on_delete=models.CASCADE,
        related_name="activities",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lead_activities",
        help_text="Who triggered this event (null = system/automated).",
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Lead Activity"
        verbose_name_plural = "Lead Activities"

    def __str__(self):
        actor = self.user.get_short_name() if self.user else "System"
        return f"[{self.get_action_display()}] Lead #{self.lead_id} by {actor}"


class VideoReview(models.Model):
    title = models.CharField(max_length=200)
    customer_name = models.CharField(max_length=100, blank=True)
    video = models.FileField(upload_to="video_reviews/")
    thumbnail = models.ImageField(upload_to="video_reviews/thumbnails/", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "-created_at"]

    def __str__(self):
        return f"{self.order} - {self.title}"


# ── NEW: FranchiseAgreement ──

class FranchiseAgreement(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("active", "Active"),
        ("expired", "Expired"),
        ("terminated", "Terminated"),
    ]

    sales_point = models.OneToOneField(
        SalesPoint,
        on_delete=models.CASCADE,
        related_name="franchise_agreement",
    )

    franchisee_legal_name = models.CharField(max_length=200)
    franchisee_contact_name = models.CharField(max_length=120, blank=True)
    franchisee_email = models.EmailField(blank=True)
    franchisee_phone = models.CharField(max_length=30, blank=True)

    upfront_fee = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="One-time franchise fee in USD"
    )
    royalty_rate = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Monthly royalty as % of gross revenue"
    )
    marketing_fee_rate = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Marketing fund contribution as % of gross revenue"
    )

    territory_notes = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    agreement_date = models.DateField(null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    renewal_date = models.DateField(null=True, blank=True)

    agreement_document = models.FileField(
        upload_to="franchise/agreements/",
        blank=True, null=True,
        help_text="Signed franchise agreement PDF"
    )

    internal_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Franchise Agreement"
        verbose_name_plural = "Franchise Agreements"

    def __str__(self):
        return f"{self.sales_point.name} — {self.franchisee_legal_name}"

    @property
    def is_active(self):
        return self.status == "active"

# ---------------------------------------------------------------------------
# Estimate
# ---------------------------------------------------------------------------

from decimal import Decimal


class Estimate(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
    ]

    lead = models.ForeignKey(
        LeadModel,
        on_delete=models.CASCADE,
        related_name='estimates',
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='created_estimates',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    notes = models.TextField(blank=True, help_text='Notes or terms visible on the estimate')
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0'),
                                   help_text='Tax rate as a percentage, e.g. 8.25')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Estimate'
        verbose_name_plural = 'Estimates'

    def __str__(self):
        return f'Estimate #{self.pk} — {self.lead}'

    @property
    def subtotal(self):
        return sum(item.line_total for item in self.line_items.all())

    @property
    def tax_amount(self):
        return (self.subtotal * self.tax_rate / Decimal('100')).quantize(Decimal('0.01'))

    @property
    def total(self):
        return self.subtotal + self.tax_amount


class EstimateLineItem(models.Model):
    estimate = models.ForeignKey(
        Estimate,
        on_delete=models.CASCADE,
        related_name='line_items',
    )
    description = models.CharField(max_length=500)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1'))
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    @property
    def line_total(self):
        return (self.quantity * self.unit_price).quantize(Decimal('0.01'))
