"""CustomLux — a cabinets-only project board that lives apart from /panel/.

Deliberately self-contained. A card on this board (`CabinetProject`) is a
*copy* of a panel lead: the contact details are snapshotted onto the card at
send time, so editing anything here never writes back to `home.LeadModel`.
The FK to the lead is kept only so we can show provenance and avoid sending
the same lead twice.

Access is not role-based like the rest of the CRM. It is: the owner email
(settings.CUSTOMLUX_OWNER_EMAIL), any superuser, or an explicitly invited
`CabinetMember`. See customlux.access.
"""
from django.conf import settings
from django.db import models


class CabinetStage(models.Model):
    """A column on the board. Admin-editable so the workflow can change.

    `code` is the stable contract (mirrors the LeadStatus convention in
    home/models.py) — branch on the code, never on the label.
    """
    code = models.SlugField(max_length=40, unique=True)
    label = models.CharField(max_length=60)
    color = models.CharField(
        max_length=7, default="#6b7280",
        help_text="Hex colour for the column header, e.g. #2563eb",
    )
    order = models.PositiveIntegerField(default=100)
    is_active = models.BooleanField(default=True)
    is_won = models.BooleanField(
        default=False, help_text="Terminal 'delivered/complete' column.",
    )
    is_lost = models.BooleanField(
        default=False, help_text="Terminal 'cancelled/dead' column.",
    )

    class Meta:
        ordering = ["order", "label"]
        verbose_name = "Cabinet stage"

    def __str__(self):
        return self.label


class CabinetProject(models.Model):
    """One cabinets job. Snapshot of a lead, or created from scratch."""

    # Provenance only — never used as the source of displayed contact info.
    # SET_NULL so deleting a lead in /panel/ can't take a cabinets job with it.
    lead = models.ForeignKey(
        "home.LeadModel", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="cabinet_projects",
    )

    # ── Snapshot copied from the lead at send time; editable here ──
    title = models.CharField(max_length=200)
    customer_name = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.CharField(max_length=255, blank=True)
    zip_code = models.CharField(max_length=10, blank=True)
    source_notes = models.TextField(
        blank=True, help_text="Message/notes copied from the lead at send time.",
    )

    # ── Cabinets-specific ──
    stage = models.ForeignKey(
        CabinetStage, on_delete=models.PROTECT, related_name="projects",
    )
    order = models.IntegerField(default=0, db_index=True)
    quoted_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
    )
    linear_feet = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True,
        help_text="Total run of cabinets, in linear feet.",
    )
    finish = models.CharField(max_length=120, blank=True)
    measure_date = models.DateField(null=True, blank=True)
    install_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    archived = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="cabinet_projects_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "-created_at"]
        verbose_name = "Cabinet project"

    def __str__(self):
        return self.title

    @property
    def display_name(self):
        return self.customer_name or self.title


class CabinetMember(models.Model):
    """Someone the owner shared the board with.

    `user` is created at invite time so the person can actually log in; the
    email is kept separately because that is what the owner types and what
    identifies the invite if the account is later renamed.
    """
    email = models.EmailField(unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        null=True, blank=True, related_name="cabinet_memberships",
    )
    can_edit = models.BooleanField(
        default=True, help_text="Off = read-only access to the board.",
    )
    is_active = models.BooleanField(default=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="cabinet_invites_sent",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["email"]
        verbose_name = "Cabinet board member"

    def __str__(self):
        return self.email


class CabinetActivity(models.Model):
    """Append-only trail per project, mirroring home.LeadActivity's shape."""
    project = models.ForeignKey(
        CabinetProject, on_delete=models.CASCADE, related_name="activities",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="cabinet_activities",
    )
    detail = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Cabinet activity"

    def __str__(self):
        return self.detail
