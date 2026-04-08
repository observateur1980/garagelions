# account/models.py
#
# Architecture:
#   MyUser      — authentication only (credentials, login, permissions)
#   Profile     — personal identity (name, photo, contact info)
#   Salesperson — business role (employment, compensation, territory, hierarchy)
#
# Separation of concerns:
#   Profile is about WHO the person is.
#   Salesperson is about WHAT ROLE they play in the business.
#   A user can have a Profile without being a Salesperson (e.g. a customer-facing
#   staff account). A Salesperson always has both a MyUser and a Profile.

from django.conf import settings
from django.db import models
from django.contrib.auth.models import BaseUserManager, AbstractBaseUser, PermissionsMixin
from django.core.validators import RegexValidator
from django.db.models.signals import post_save
from django.dispatch import receiver
from PIL import Image

USERNAME_REGEX = r'^[a-zA-Z0-9.+-]*$'


# ---------------------------------------------------------------------------
# MyUser — authentication layer only
# ---------------------------------------------------------------------------

class MyUserManager(BaseUserManager):
    def create_user(self, username, email, password=None):
        if not email:
            raise ValueError('Users must have an email address')
        user = self.model(
            username=username,
            email=self.normalize_email(email),
        )
        user.is_active = True
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password):
        user = self.create_user(username, email, password=password)
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.save(using=self._db)
        return user


class MyUser(AbstractBaseUser, PermissionsMixin):
    username = models.CharField(
        max_length=120,
        unique=True,
        validators=[RegexValidator(
            regex=USERNAME_REGEX,
            message='Username must be alphanumeric',
            code='invalid_username',
        )],
    )
    email = models.EmailField(
        verbose_name='email address',
        max_length=255,
        unique=True,
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = MyUserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return self.email

    def get_full_name(self):
        try:
            return self.profile.full_name
        except Profile.DoesNotExist:
            return self.username

    def get_short_name(self):
        try:
            return self.profile.first_name or self.username
        except Profile.DoesNotExist:
            return self.username

    @property
    def role(self):
        """Convenience — returns the Salesperson role or None."""
        try:
            return self.salesperson.role
        except Salesperson.DoesNotExist:
            return None

    @property
    def is_salesperson(self):
        return hasattr(self, 'salesperson') and self.salesperson is not None

    @property
    def can_see_all_leads(self):
        """Staff, superusers, and territory managers see all leads."""
        if self.is_superuser or self.is_staff:
            return True
        try:
            return self.salesperson.role in (
                Salesperson.TERRITORY_MANAGER,
                Salesperson.LOCATION_MANAGER,
            )
        except Salesperson.DoesNotExist:
            return False


# ---------------------------------------------------------------------------
# Profile — personal identity layer
# ---------------------------------------------------------------------------

def profile_photo_upload(instance, filename):
    ext = filename.rsplit('.', 1)[-1].lower()
    return f'profiles/{instance.user.username}/photo.{ext}'


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
    )

    # Identity
    first_name = models.CharField(max_length=120, blank=True, null=True)
    last_name = models.CharField(max_length=120, blank=True, null=True)
    photo = models.ImageField(
        upload_to=profile_photo_upload,
        blank=True, null=True,
    )
    bio = models.TextField(
        blank=True,
        help_text='Short personal bio — not visible to customers.',
    )

    # Contact
    phone = models.CharField(max_length=30, blank=True)
    mobile = models.CharField(max_length=30, blank=True)
    direct_email = models.EmailField(
        blank=True,
        help_text='Work email if different from login email.',
    )

    # Location
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    timezone = models.CharField(
        max_length=60,
        blank=True,
        default='America/Los_Angeles',
    )

    # Online presence
    linkedin_url = models.URLField(blank=True)
    calendly_url = models.URLField(
        blank=True,
        help_text='Calendly or Cal.com booking link.',
    )

    # Notification preferences
    notify_new_lead_email = models.BooleanField(
        default=True,
        help_text='Email me when a new lead is assigned.',
    )
    notify_new_lead_sms = models.BooleanField(
        default=False,
        help_text='SMS me when a new lead is assigned.',
    )

    # Emergency contact
    emergency_contact_name = models.CharField(max_length=120, blank=True)
    emergency_contact_phone = models.CharField(max_length=30, blank=True)

    # Audit
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Profile'
        verbose_name_plural = 'Profiles'

    def __str__(self):
        return f'{self.full_name} (@{self.user.username})'

    @property
    def full_name(self):
        parts = [self.first_name or '', self.last_name or '']
        name = ' '.join(p for p in parts if p).strip()
        return name or self.user.username

    @property
    def display_email(self):
        return self.direct_email or self.user.email

    @property
    def display_phone(self):
        return self.mobile or self.phone

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.photo:
            try:
                img = Image.open(self.photo.path)
                if img.width > 400 or img.height > 400:
                    img.thumbnail((400, 400))
                    img.save(self.photo.path)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Salesperson — business role layer
# ---------------------------------------------------------------------------

class Salesperson(models.Model):
    """
    Represents a person's role within the Garage Lions business.
    Separate from Profile (who they are) and MyUser (how they log in).

    Role hierarchy:
        SALESPERSON       – works individual leads at one location
        LOCATION_MANAGER  – runs a SalesPoint, sees their whole team
        TERRITORY_MANAGER – oversees multiple locations, corporate view
    """

    # Role choices
    SALESPERSON = 'salesperson'
    LOCATION_MANAGER = 'location_manager'
    TERRITORY_MANAGER = 'territory_manager'

    ROLE_CHOICES = [
        (SALESPERSON, 'Salesperson'),
        (LOCATION_MANAGER, 'Location Manager'),
        (TERRITORY_MANAGER, 'Territory Manager'),
    ]

    # Employment type choices
    W2 = 'w2'
    CONTRACTOR_1099 = '1099'
    FRANCHISE_OWNER = 'franchise_owner'

    EMPLOYMENT_CHOICES = [
        (W2, 'W-2 Employee'),
        (CONTRACTOR_1099, '1099 Contractor'),
        (FRANCHISE_OWNER, 'Franchise Owner'),
    ]

    # Status choices
    ACTIVE = 'active'
    ON_LEAVE = 'on_leave'
    TERMINATED = 'terminated'

    STATUS_CHOICES = [
        (ACTIVE, 'Active'),
        (ON_LEAVE, 'On Leave'),
        (TERMINATED, 'Terminated'),
    ]

    # Core links
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='salesperson',
    )
    sales_point = models.ForeignKey(
        'home.SalesPoint',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='salespeople',
        help_text='Primary location this person is assigned to.',
    )

    # Hierarchy — manager is another Salesperson record (self-referential)
    manager = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='direct_reports',
        help_text='Who this person reports to.',
    )

    # Role & status
    role = models.CharField(
        max_length=30,
        choices=ROLE_CHOICES,
        default=SALESPERSON,
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=ACTIVE,
    )
    employment_type = models.CharField(
        max_length=20,
        choices=EMPLOYMENT_CHOICES,
        default=W2,
    )

    # Compensation
    base_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Annual base salary in USD (if applicable).',
    )
    commission_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Commission percentage on closed deals (e.g. 5.00 = 5%).',
    )
    draw_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Monthly draw against commission (if applicable).',
    )

    # Employment dates
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(
        null=True,
        blank=True,
        help_text='Leave blank if currently active.',
    )

    # Territory — for territory managers who oversee multiple locations
    # Individual salesperson territory comes from their SalesPoint ZIP codes.
    territory_notes = models.TextField(
        blank=True,
        help_text='For territory managers: description of their oversight area.',
    )

    # Internal HR notes (admin-only)
    internal_notes = models.TextField(blank=True)

    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Salesperson'
        verbose_name_plural = 'Salespeople'
        ordering = ['user__profile__last_name', 'user__profile__first_name']

    def __str__(self):
        return f'{self.user.get_full_name()} — {self.get_role_display()}'

    @property
    def full_name(self):
        return self.user.get_full_name()

    @property
    def is_active(self):
        return self.status == self.ACTIVE

    @property
    def direct_report_count(self):
        return self.direct_reports.count()

    def get_visible_sales_points(self):
        """
        Returns the QuerySet of SalesPoints this person can see leads for.
        - Salesperson: only their assigned sales_point
        - Location Manager: only their assigned sales_point
        - Territory Manager: all active sales_points
        """
        from home.models import SalesPoint
        if self.role == self.TERRITORY_MANAGER:
            return SalesPoint.objects.filter(is_active=True)
        if self.sales_point:
            return SalesPoint.objects.filter(pk=self.sales_point_id)
        return SalesPoint.objects.none()


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_profile_on_user_create(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)