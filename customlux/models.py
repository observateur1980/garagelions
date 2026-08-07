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
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import models

_CENTS = Decimal("0.01")


def _money(value):
    return Decimal(value or 0).quantize(_CENTS, rounding=ROUND_HALF_UP)


class CabinetSettings(models.Model):
    """Single row of board-wide settings, editable at /customlux/settings/.

    Kept in the DB rather than in settings.py so the owner can change the
    commission split without a deploy.
    """
    BASIS_MARKUP = "markup"
    BASIS_SHARE = "share"
    BASIS_CHOICES = [
        (BASIS_MARKUP, "Markup added on top of CustomLux's price"),
        (BASIS_SHARE, "Share taken out of the deal total"),
    ]

    commission_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("30.00"),
        help_text="Percent of the pre-tax deal amount owed to Garage Lions.",
    )
    # How that percent is applied. `markup` matches how CustomLux actually
    # invoices: they quote their own price, add the percentage on top, and the
    # customer pays the sum — so the cut is rate/(100+rate) of the total, not
    # rate/100. A $5,200 sale at 30% markup pays $1,200, not $1,560.
    commission_basis = models.CharField(
        max_length=10, choices=BASIS_CHOICES, default=BASIS_MARKUP,
    )

    COLLECTED_CUSTOMLUX = "customlux"
    COLLECTED_GARAGELIONS = "garagelions"
    COLLECTED_CHOICES = [
        (COLLECTED_CUSTOMLUX, "CustomLux collects from the customer"),
        (COLLECTED_GARAGELIONS, "Garage Lions collects from the customer"),
    ]
    # Which way money usually flows. Whoever banks the customer's cheque owes
    # the other side their share, so this decides whether a deal is money in
    # or money out. Overridable per deal.
    default_collected_by = models.CharField(
        max_length=20, choices=COLLECTED_CHOICES, default=COLLECTED_CUSTOMLUX,
    )
    default_deposit_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("50.00"),
        help_text="Down payment percent used to pre-fill a new deal.",
    )
    default_tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00"),
        help_text=(
            "Sales-tax percent used to pre-fill the tax field on a new deal. "
            "Tax is always excluded from the commission base."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "CustomLux settings"
        verbose_name_plural = "CustomLux settings"

    def __str__(self):
        return f"Commission {self.commission_rate}%"

    @classmethod
    def get(cls):
        obj = cls.objects.first()
        if obj is None:
            obj = cls.objects.create()
        return obj


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
    # Deprecated: the lead's message is no longer copied across, and the board
    # no longer displays this. Kept only so existing rows aren't destroyed —
    # nothing reads or writes it. Safe to drop once those rows aren't wanted.
    source_notes = models.TextField(blank=True)

    # ── Cabinets-specific ──
    stage = models.ForeignKey(
        CabinetStage, on_delete=models.PROTECT, related_name="projects",
    )
    order = models.IntegerField(default=0, db_index=True)
    # The full figure the customer pays, sales tax included.
    quoted_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Deal total (incl. tax)",
    )
    # Excluded from the commission base — the split is on the pre-tax amount.
    tax_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Sales tax included in the total",
    )
    # Blank = use the board-wide rate from CabinetSettings. Set only when a
    # particular deal was agreed at a different split.
    commission_rate = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        verbose_name="Commission rate for this deal (%)",
    )
    # Blank = use the board-wide default deposit percent.
    deposit_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        verbose_name="Deposit %",
    )
    # Blank = use the board default. Decides which way the settlement runs.
    collected_by = models.CharField(
        max_length=20, blank=True,
        choices=[("", "Board default")] + CabinetSettings.COLLECTED_CHOICES,
        verbose_name="Who the customer pays",
    )
    # Deprecated: removed from the UI and from the form. No row ever carried a
    # value. Columns kept so no data can be destroyed; safe to drop.
    linear_feet = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True,
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

    # ── Commission maths ────────────────────────────────────────────
    # Sales tax is always taken out first; the split is on the pre-tax amount.
    # How the percentage is then applied depends on CabinetSettings.basis:
    #
    #   markup (default, matches CustomLux's invoices)
    #       their price + rate% of their price = net
    #       commission = net × rate / (100 + rate)
    #       e.g. $5,200 net at 30% -> $1,200 (their price was $4,000)
    #
    #   share
    #       commission = net × rate / 100
    #       e.g. $5,200 net at 30% -> $1,560

    @property
    def effective_commission_rate(self):
        if self.commission_rate is not None:
            return self.commission_rate
        return CabinetSettings.get().commission_rate

    @property
    def commission_basis(self):
        return CabinetSettings.get().commission_basis

    # ── Contract value, including any changes agreed mid-job ────────
    # `quoted_amount` is the ORIGINAL contract. Change orders sit on top as
    # signed rows, so `current_total` is what everything downstream — tax base,
    # commission, deposit, customer balance — is calculated from. Editing the
    # original amount and adding a change order both work; the difference is
    # that a change order keeps the history of what was agreed and when.

    @property
    def change_total(self):
        # Unsaved instances have no related rows yet — the settings page builds
        # one to render its worked example.
        if self.pk is None:
            return _money(0)
        return _money(sum(c.amount for c in self.change_orders.all()))

    @property
    def current_total(self):
        """Deal total after change orders. None until an amount is entered."""
        if self.quoted_amount is None:
            return None
        return _money(self.quoted_amount + self.change_total)

    @property
    def has_changes(self):
        return self.pk is not None and self.change_orders.exists()

    @property
    def net_amount(self):
        """Pre-tax amount the commission is calculated on."""
        total = self.current_total
        if total is None:
            return None
        return _money(total - (self.tax_amount or 0))

    # ── Deposit ─────────────────────────────────────────────────────
    @property
    def effective_deposit_percent(self):
        if self.deposit_percent is not None:
            return self.deposit_percent
        return CabinetSettings.get().default_deposit_percent

    @property
    def deposit_amount(self):
        total = self.current_total
        if total is None:
            return None
        return _money(total * self.effective_deposit_percent / Decimal(100))

    # ── What the customer has actually paid ─────────────────────────
    @property
    def customer_paid(self):
        if self.pk is None:
            return _money(0)
        return _money(sum(p.amount for p in self.customer_payments.all()))

    @property
    def customer_balance(self):
        total = self.current_total
        if total is None:
            return None
        return _money(total - self.customer_paid)

    @property
    def deposit_covered(self):
        """True once the customer has paid at least the deposit."""
        dep = self.deposit_amount
        return dep is not None and dep > 0 and self.customer_paid >= dep

    @property
    def customer_paid_in_full(self):
        bal = self.customer_balance
        return bal is not None and bal <= 0 and self.customer_paid > 0

    @property
    def customer_percent_paid(self):
        total = self.current_total
        if not total:
            return Decimal(0)
        pct = self.customer_paid / total * Decimal(100)
        return min(Decimal(100), _money(pct))

    @property
    def commission_amount(self):
        """What the subcontractor owes Garage Lions on this deal."""
        net = self.net_amount
        if net is None:
            return None
        rate = self.effective_commission_rate
        if self.commission_basis == CabinetSettings.BASIS_MARKUP:
            return _money(net * rate / (Decimal(100) + rate))
        return _money(net * rate / Decimal(100))

    @property
    def subcontractor_price(self):
        """CustomLux's own pre-tax price — the figure the markup sits on."""
        net = self.net_amount
        if net is None:
            return None
        return _money(net - (self.commission_amount or 0))

    @property
    def subcontractor_amount(self):
        """What CustomLux keeps out of the total, tax included."""
        total = self.current_total
        if total is None:
            return None
        return _money(total - (self.commission_amount or 0))

    @property
    def has_custom_rate(self):
        return self.commission_rate is not None

    # ── Settlement ──────────────────────────────────────────────────
    # Whoever banks the customer's cheque owes the other side their share:
    #
    #   CustomLux collects  -> they owe us the commission        (money IN)
    #   Garage Lions collects -> we owe them the rest of the deal (money OUT)
    #
    # Either way we end up ahead by the commission; only the direction of the
    # transfer differs, and getting it wrong would point "outstanding" the
    # wrong way on half the deals.

    @property
    def effective_collected_by(self):
        return self.collected_by or CabinetSettings.get().default_collected_by

    @property
    def we_collect(self):
        return self.effective_collected_by == CabinetSettings.COLLECTED_GARAGELIONS

    @property
    def settlement_direction(self):
        """'out' when we owe CustomLux, 'in' when they owe us."""
        return "out" if self.we_collect else "in"

    @property
    def settlement_expected(self):
        """How much should change hands, in `settlement_direction`."""
        if self.current_total is None:
            return None
        return self.subcontractor_amount if self.we_collect else self.commission_amount

    @property
    def settlement_transferred(self):
        """Net moved so far, counted toward the expected direction."""
        if self.pk is None:
            return _money(0)
        received = sum(
            p.amount for p in self.payments.all()
            if p.direction == CabinetPayment.DIR_IN
        )
        sent = sum(
            p.amount for p in self.payments.all()
            if p.direction == CabinetPayment.DIR_OUT
        )
        net = sent - received if self.we_collect else received - sent
        return _money(net)

    @property
    def settlement_outstanding(self):
        expected = self.settlement_expected
        if expected is None:
            return None
        return _money(expected - self.settlement_transferred)

    @property
    def is_settled(self):
        out = self.settlement_outstanding
        return (
            out is not None and out <= 0 and self.settlement_transferred > 0
        )

    @property
    def is_part_paid(self):
        out = self.settlement_outstanding
        return (
            self.settlement_transferred > 0 and out is not None and out > 0
        )

    # Kept for the board summary: what we net on this deal either way.
    @property
    def commission_paid(self):
        return self.settlement_transferred if not self.we_collect else _money(0)


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


class CabinetTodo(models.Model):
    """Checklist on a cabinets job. Mirrors home.LeadTodo's shape."""
    project = models.ForeignKey(
        CabinetProject, on_delete=models.CASCADE, related_name="todos",
    )
    title = models.CharField(max_length=255)
    is_completed = models.BooleanField(default=False)
    due_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="cabinet_todos_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["is_completed", "-created_at"]
        verbose_name = "Cabinet to-do"

    def __str__(self):
        return self.title


class CabinetEstimate(models.Model):
    """An estimate on a cabinets job — a file, deliberately.

    Panel builds estimates from line items (home.Estimate). CustomLux quotes
    its own work, so all we keep is whatever document they send over.
    """
    project = models.ForeignKey(
        CabinetProject, on_delete=models.CASCADE, related_name="estimates",
    )
    file = models.FileField(upload_to="customlux_estimates/%Y/%m/")
    label = models.CharField(
        max_length=140, blank=True,
        help_text="Optional — e.g. “Revised after site visit”.",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="cabinet_estimates_uploaded",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at", "-id"]
        verbose_name = "Cabinet estimate file"

    def __str__(self):
        return self.filename

    @property
    def filename(self):
        return (self.file.name or "").rsplit("/", 1)[-1]

    @property
    def size_display(self):
        try:
            kb = self.file.size / 1024
        except (OSError, ValueError):
            return ""
        if kb < 1024:
            return f"{kb:.0f} KB"
        return f"{kb / 1024:.1f} MB"


class CabinetPayment(models.Model):
    """A commission payment actually received from CustomLux.

    Separate rows rather than a single paid/unpaid flag so part-payments and
    a real payment history are both possible.
    """
    METHOD_CHOICES = [
        ("", "—"),
        ("check", "Check"),
        ("zelle", "Zelle"),
        ("transfer", "Bank transfer"),
        ("cash", "Cash"),
        ("card", "Card"),
        ("other", "Other"),
    ]

    DIR_IN = "in"
    DIR_OUT = "out"
    DIRECTION_CHOICES = [
        (DIR_IN, "Received from CustomLux"),
        (DIR_OUT, "Sent to CustomLux"),
    ]

    project = models.ForeignKey(
        CabinetProject, on_delete=models.CASCADE, related_name="payments",
    )
    direction = models.CharField(
        max_length=4, choices=DIRECTION_CHOICES, default=DIR_IN,
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    received_on = models.DateField()
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, blank=True)
    reference = models.CharField(
        max_length=120, blank=True, help_text="Cheque number, transfer ref…",
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="cabinet_payments_recorded",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_on", "-id"]
        verbose_name = "Commission payment"

    def __str__(self):
        return f"${self.amount} on {self.received_on}"


class CabinetChangeOrder(models.Model):
    """A mid-job price change agreed with the customer.

    Signed: positive for extra work, negative when scope is cut. Stored as
    rows rather than by editing the original amount so the contract history
    survives — and because commission, deposit and balances all recompute from
    `CabinetProject.current_total`, which includes these.
    """
    project = models.ForeignKey(
        CabinetProject, on_delete=models.CASCADE, related_name="change_orders",
    )
    description = models.CharField(max_length=200)
    amount = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text="Positive to add, negative to reduce.",
    )
    dated = models.DateField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="cabinet_changes_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["dated", "id"]
        verbose_name = "Change order"

    def __str__(self):
        return f"{self.description} ({self.amount:+})"

    @property
    def is_increase(self):
        return self.amount >= 0


class CabinetCustomerPayment(models.Model):
    """Money the customer has actually handed over.

    Separate from CabinetPayment, which tracks the Garage Lions ↔ CustomLux
    settlement. Both can exist on one job and they answer different questions:
    has the customer paid us, versus have we squared up with the subcontractor.
    """
    project = models.ForeignKey(
        CabinetProject, on_delete=models.CASCADE, related_name="customer_payments",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    received_on = models.DateField()
    is_deposit = models.BooleanField(
        default=False, verbose_name="This is the deposit / down payment",
    )
    method = models.CharField(
        max_length=20, choices=CabinetPayment.METHOD_CHOICES, blank=True,
    )
    reference = models.CharField(max_length=120, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="cabinet_customer_payments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_on", "-id"]
        verbose_name = "Customer payment"

    def __str__(self):
        return f"${self.amount} on {self.received_on}"


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
