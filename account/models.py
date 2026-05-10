# account/models.py
#
# Architecture:
#   MyUser         — authentication only (credentials, login, permissions)
#   Profile        — personal identity (name, photo, contact info)
#   ProjectManager — business role (employment, compensation, territory, hierarchy)
#
# Separation of concerns:
#   Profile is about WHO the person is.
#   ProjectManager is about WHAT ROLE they play in the business.
#   A user can have a Profile without being a ProjectManager (e.g. a customer-facing
#   staff account). A ProjectManager always has both a MyUser and a Profile.

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
        """Convenience — returns the ProjectManager role or None."""
        try:
            return self.project_manager.role
        except ProjectManager.DoesNotExist:
            return None

    @property
    def is_project_manager(self):
        return hasattr(self, 'project_manager') and self.project_manager is not None

    @property
    def can_see_all_leads(self):
        """Staff, superusers, and territory managers see all leads."""
        if self.is_superuser or self.is_staff:
            return True
        try:
            return self.project_manager.role in (
                ProjectManager.TERRITORY_MANAGER,
                ProjectManager.LOCATION_MANAGER,
            )
        except ProjectManager.DoesNotExist:
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
# Role — admin-managed catalog of business roles
# ---------------------------------------------------------------------------

class Role(models.Model):
    """Admin-managed list of business roles.

    ProjectManager.role stores the `code` of one of these rows. The Role
    table governs which codes the UI offers, the human label, and two
    capability flags that the rest of the app consults:

      - allows_multiple_locations: when True, the user may have entries in
        ProjectManager.extra_sales_points; when False, only the primary
        sales_point is allowed.
      - sees_all_locations: when True, the user sees leads from every
        active SalesPoint regardless of their assignments.

    Codes for the three seeded roles are referenced from elsewhere in the
    codebase (see ProjectManager.PROJECT_MANAGER / LOCATION_MANAGER /
    TERRITORY_MANAGER constants), so those rows are flagged is_protected
    and cannot be deleted from the admin.
    """

    code = models.SlugField(
        max_length=40, unique=True,
        help_text="Stable identifier referenced in code; lower_snake_case.",
    )
    label = models.CharField(max_length=80)
    description = models.TextField(blank=True)
    allows_multiple_locations = models.BooleanField(
        default=False,
        help_text="If on, this role can be assigned more than one sales point.",
    )
    sees_all_locations = models.BooleanField(
        default=False,
        help_text="If on, members of this role see leads from every active sales point, regardless of assignment.",
    )
    is_protected = models.BooleanField(
        default=False,
        help_text="Protected roles are referenced by code elsewhere in the app and cannot be deleted.",
    )
    order = models.PositiveIntegerField(default=100)

    class Meta:
        ordering = ['order', 'label']
        verbose_name = 'Role'
        verbose_name_plural = 'Roles'

    def __str__(self):
        return self.label

    @classmethod
    def as_choices(cls):
        return list(cls.objects.values_list('code', 'label'))


# ---------------------------------------------------------------------------
# ProjectManager — business role layer
# ---------------------------------------------------------------------------

class ProjectManager(models.Model):
    """
    Represents a person's role within the Garage Lions business.
    Separate from Profile (who they are) and MyUser (how they log in).

    Role behavior is governed by the Role table (admin-managed). The
    constants below are the codes of the three seeded rows and exist
    only so legacy comparisons elsewhere in the codebase keep working.
    """

    # Codes of the three seeded Role rows (kept for backwards compatibility
    # with code that compares ProjectManager.role to a hardcoded string).
    PROJECT_MANAGER = 'project_manager'
    LOCATION_MANAGER = 'location_manager'
    TERRITORY_MANAGER = 'territory_manager'

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
        related_name='project_manager',
    )
    sales_point = models.ForeignKey(
        'home.SalesPoint',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='project_managers',
        help_text='Primary location this person is assigned to.',
    )
    extra_sales_points = models.ManyToManyField(
        'home.SalesPoint',
        blank=True,
        related_name='extra_project_managers',
        help_text='Additional locations this person manages.',
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
    # Allowed values are governed by the Role table (admin-managed), not a
    # hardcoded list. Keeping choices= off the field prevents Django admin
    # from silently overwriting custom codes with the default during a
    # save sweep — same fix used on LeadModel.status.
    role = models.CharField(
        max_length=40,
        default=PROJECT_MANAGER,
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
        verbose_name = 'Project Manager'
        verbose_name_plural = 'Project Managers'
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

    @property
    def role_obj(self):
        """Return the Role row matching self.role, or None if missing."""
        if not self.role:
            return None
        try:
            return Role.objects.get(code=self.role)
        except Role.DoesNotExist:
            return None

    def get_role_display(self):
        r = self.role_obj
        if r:
            return r.label
        return (self.role or '').replace('_', ' ').title() or '—'

    @property
    def allows_multiple_locations(self):
        r = self.role_obj
        if r:
            return r.allows_multiple_locations
        return self.role in (self.LOCATION_MANAGER, self.TERRITORY_MANAGER)

    @property
    def sees_all_locations(self):
        r = self.role_obj
        if r:
            return r.sees_all_locations
        return self.role == self.TERRITORY_MANAGER

    def get_visible_sales_points(self):
        """QuerySet of SalesPoints this person can see leads for.

        Driven by Role flags:
          - sees_all_locations=True  → every active SalesPoint
          - allows_multiple_locations → primary + extras
          - otherwise                → primary only
        """
        from home.models import SalesPoint
        if self.sees_all_locations:
            return SalesPoint.objects.filter(is_active=True)
        pks = []
        if self.sales_point_id:
            pks.append(self.sales_point_id)
        if self.allows_multiple_locations and self.pk:
            pks.extend(self.extra_sales_points.values_list('pk', flat=True))
        if pks:
            return SalesPoint.objects.filter(pk__in=pks)
        return SalesPoint.objects.none()

    @property
    def assigned_sales_points(self):
        """SalesPoints where this user is `SalesPoint.assigned_user`.

        Independent of `sales_point` / `extra_sales_points` — that pair
        models employment ('home base' + extras), while this models the
        SP-side ownership ('who's the point of contact for this SP').
        """
        from home.models import SalesPoint
        if not self.user_id:
            return SalesPoint.objects.none()
        return SalesPoint.objects.filter(assigned_user_id=self.user_id)

    @property
    def connected_sales_points(self):
        """Union of every SalesPoint connected to this user, with provenance.

        Returns list of (sales_point, list_of_tags) where tags are any of:
        'primary', 'extra', 'assigned_user'. Used by the admin change page
        so the user can see at a glance why each SP shows up.
        """
        bag = {}

        def tag(sp, name):
            entry = bag.setdefault(sp.pk, (sp, []))
            if name not in entry[1]:
                entry[1].append(name)

        if self.sales_point_id:
            tag(self.sales_point, 'primary')
        if self.pk:
            for sp in self.extra_sales_points.all():
                tag(sp, 'extra')
        for sp in self.assigned_sales_points:
            tag(sp, 'assigned_user')

        return sorted(bag.values(), key=lambda pair: (pair[0].order, pair[0].name))

    @property
    def managed_sales_points(self):
        """Concrete list of SalesPoints this person manages (display use).

        For sees_all_locations roles this returns every active SP — same
        as get_visible_sales_points — but evaluated as a list so admin
        templates can call len() without re-querying.
        """
        return list(self.get_visible_sales_points().order_by('order', 'name'))

    def clean(self):
        super().clean()
        # Block extras when role disallows multiple locations.
        if self.pk and not self.allows_multiple_locations:
            from django.core.exceptions import ValidationError
            if self.extra_sales_points.exists():
                raise ValidationError({
                    'extra_sales_points':
                        f"The role '{self.get_role_display()}' is configured "
                        "for a single location. Remove extra sales points or "
                        "switch to a role that allows multiple locations.",
                })


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_profile_on_user_create(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)