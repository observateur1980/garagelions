from decimal import Decimal
from django.db import models
from django.conf import settings


# ── Customer ────────────────────────────────────────────────────────
class Customer(models.Model):
    sales_point = models.ForeignKey(
        "home.SalesPoint", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="panel_customers",
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=50, blank=True)
    zip_code = models.CharField(max_length=10, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


# ── Project ─────────────────────────────────────────────────────────
class Project(models.Model):
    STATUS_CHOICES = [
        ("not_started", "Not Started"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("canceled", "Canceled"),
    ]

    name = models.CharField(max_length=255)
    sales_point = models.ForeignKey(
        "home.SalesPoint", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="panel_projects",
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name="projects"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="not_started")
    description = models.TextField(blank=True)
    start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


# ── Part Category ───────────────────────────────────────────────────
class PartCategory(models.Model):
    """
    Global category: sales_point is NULL (created by admin/superuser).
    Local category: sales_point is set (created by a location user).
    """
    name = models.CharField(max_length=100)
    sales_point = models.ForeignKey(
        "home.SalesPoint", on_delete=models.CASCADE,
        null=True, blank=True, related_name="part_categories",
        help_text="NULL = global category, set = local to this location.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Part categories"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "sales_point"],
                name="unique_category_per_location",
            ),
            models.UniqueConstraint(
                fields=["name"],
                condition=models.Q(sales_point__isnull=True),
                name="unique_global_category_name",
            ),
        ]

    @property
    def is_global(self):
        return self.sales_point_id is None

    def __str__(self):
        if self.is_global:
            return self.name
        return f"{self.name} (local)"


# ── SalesPoint ↔ Global Category join table ─────────────────────────
class SalesPointPartCategory(models.Model):
    """Tracks which global categories a SalesPoint has enabled."""
    sales_point = models.ForeignKey(
        "home.SalesPoint", on_delete=models.CASCADE,
        related_name="enabled_part_categories",
    )
    category = models.ForeignKey(
        PartCategory, on_delete=models.CASCADE,
        limit_choices_to={"sales_point__isnull": True},
    )

    class Meta:
        unique_together = ("sales_point", "category")

    def __str__(self):
        return f"{self.sales_point} → {self.category}"


# ── Unit ────────────────────────────────────────────────────────────
class Unit(models.Model):
    """
    Global unit: sales_point is NULL (admin-created).
    Local unit: sales_point is set (created by a location user).
    """
    name = models.CharField(max_length=50)
    abbreviation = models.CharField(max_length=10)
    sales_point = models.ForeignKey(
        "home.SalesPoint", on_delete=models.CASCADE,
        null=True, blank=True, related_name="units",
        help_text="NULL = global unit, set = local to this location.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["name", "sales_point"],
                name="unique_unit_per_location",
            ),
            models.UniqueConstraint(
                fields=["name"],
                condition=models.Q(sales_point__isnull=True),
                name="unique_global_unit_name",
            ),
        ]

    @property
    def is_global(self):
        return self.sales_point_id is None

    def __str__(self):
        return f"{self.name} ({self.abbreviation})"


# ── SalesPoint ↔ Global Unit join table ─────────────────────────────
class SalesPointUnit(models.Model):
    """Tracks which global units a SalesPoint has enabled."""
    sales_point = models.ForeignKey(
        "home.SalesPoint", on_delete=models.CASCADE,
        related_name="enabled_units",
    )
    unit = models.ForeignKey(
        Unit, on_delete=models.CASCADE,
        limit_choices_to={"sales_point__isnull": True},
    )

    class Meta:
        unique_together = ("sales_point", "unit")

    def __str__(self):
        return f"{self.sales_point} → {self.unit}"


# ── SalesPoint ↔ Global Part join table ──────────────────────────────
class SalesPointPart(models.Model):
    """Tracks which global parts a SalesPoint has enabled, with local overrides."""
    sales_point = models.ForeignKey(
        "home.SalesPoint", on_delete=models.CASCADE,
        related_name="enabled_parts",
    )
    part = models.ForeignKey(
        "Part", on_delete=models.CASCADE,
        limit_choices_to={"sales_point__isnull": True},
    )
    custom_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
    )
    custom_unit = models.ForeignKey(
        Unit, on_delete=models.SET_NULL, null=True, blank=True,
        help_text="Override the unit for this location.",
    )

    class Meta:
        unique_together = ("sales_point", "part")

    @property
    def effective_price(self):
        if self.custom_price is not None:
            return self.custom_price
        return Decimal("0.00")

    @property
    def effective_unit(self):
        if self.custom_unit is not None:
            return self.custom_unit
        return self.part.unit

    def __str__(self):
        return f"{self.sales_point} → {self.part}"


# ── Part ────────────────────────────────────────────────────────────
class Part(models.Model):
    """
    Global part: sales_point is NULL (admin-created, available to all locations).
    Local part: sales_point is set (created by a location user, only for them).
    """
    name = models.CharField(max_length=200)
    sales_point = models.ForeignKey(
        "home.SalesPoint", on_delete=models.CASCADE,
        null=True, blank=True, related_name="parts",
        help_text="NULL = global part, set = local to this location.",
    )
    sku = models.CharField(max_length=50, blank=True)
    category = models.ForeignKey(
        PartCategory, on_delete=models.SET_NULL, null=True, blank=True
    )
    unit = models.ForeignKey(Unit, on_delete=models.SET_NULL, null=True, blank=True)
    unit_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Only used for local parts. Global parts have no price — each location sets their own.",
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


# ── Estimate ────────────────────────────────────────────────────────
class Estimate(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("sent", "Sent"),
        ("approved", "Approved"),
        ("declined", "Declined"),
        ("expired", "Expired"),
        ("converted", "Converted"),
    ]

    estimate_number = models.CharField(max_length=30, unique=True)
    title = models.CharField(max_length=255)
    sales_point = models.ForeignKey(
        "home.SalesPoint", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="panel_estimates",
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name="estimates"
    )
    project = models.OneToOneField(
        Project, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="estimate"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    description = models.TextField(blank=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    declined_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.estimate_number} — {self.title}"

    @property
    def is_editable(self):
        return self.status == "draft"

    def recalc_totals(self):
        self.subtotal = sum(item.line_total for item in self.items.all())
        self.tax = self.subtotal * self.tax_rate / 100
        self.total = self.subtotal + self.tax
        self.save(update_fields=["subtotal", "tax", "total"])


class EstimateItem(models.Model):
    estimate = models.ForeignKey(
        Estimate, on_delete=models.CASCADE, related_name="items"
    )
    part = models.ForeignKey(Part, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category_label = models.CharField(max_length=100, blank=True)
    unit_label = models.CharField(max_length=50, blank=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.name

    @property
    def line_total(self):
        return self.quantity * self.unit_price


# ── Invoice ─────────────────────────────────────────────────────────
class Invoice(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("sent", "Sent"),
        ("paid", "Paid"),
        ("partial", "Partially Paid"),
        ("overdue", "Overdue"),
        ("canceled", "Canceled"),
    ]

    invoice_number = models.CharField(max_length=30, unique=True)
    title = models.CharField(max_length=255)
    sales_point = models.ForeignKey(
        "home.SalesPoint", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="panel_invoices",
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name="invoices"
    )
    estimate = models.OneToOneField(
        Estimate, on_delete=models.SET_NULL, null=True, blank=True
    )
    project = models.ForeignKey(
        Project, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="invoices"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.invoice_number} — {self.title}"

    @property
    def balance_due(self):
        return self.total - self.amount_paid


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name="items"
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    @property
    def line_total(self):
        return self.quantity * self.unit_price


# ── Transaction ─────────────────────────────────────────────────────
class Transaction(models.Model):
    TYPE_CHOICES = [
        ("payment", "Payment"),
        ("refund", "Refund"),
        ("expense", "Expense"),
    ]

    invoice = models.ForeignKey(
        Invoice, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="transactions"
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True
    )
    transaction_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default="payment")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.get_transaction_type_display()} — ${self.amount}"


# ── Task ────────────────────────────────────────────────────────────
class TaskList(models.Model):
    name = models.CharField(max_length=100)
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, null=True, blank=True,
        related_name="task_lists"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.name


class Task(models.Model):
    RECURRENCE_CHOICES = [
        ("none", "None"),
        ("daily", "Daily"),
        ("weekly", "Weekly"),
        ("monthly", "Monthly"),
        ("annually", "Annually"),
    ]

    task_list = models.ForeignKey(
        TaskList, on_delete=models.CASCADE, related_name="tasks"
    )
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True,
        related_name="subtasks"
    )
    title = models.CharField(max_length=255)
    notes = models.TextField(blank=True)
    is_completed = models.BooleanField(default=False)
    is_starred = models.BooleanField(default=False)
    due_date = models.DateField(null=True, blank=True)
    due_time = models.TimeField(null=True, blank=True)
    recurrence = models.CharField(max_length=20, choices=RECURRENCE_CHOICES, default="none")
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.title
