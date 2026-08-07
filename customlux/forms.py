from django import forms
from django.forms import modelformset_factory
from django.utils import timezone

from .models import (
    CabinetChangeOrder, CabinetCustomerPayment, CabinetEstimate, CabinetPayment,
    CabinetProject, CabinetSettings, CabinetStage, CabinetTodo,
)

_FC = "form-control"
_FS = "form-select"


class CabinetProjectForm(forms.ModelForm):
    class Meta:
        model = CabinetProject
        fields = [
            "title", "customer_name", "email", "phone", "address", "zip_code",
            "stage", "quoted_amount", "tax_amount", "commission_rate",
            "collected_by", "deposit_percent",
            "measure_date", "install_date", "notes",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": _FC}),
            "customer_name": forms.TextInput(attrs={"class": _FC}),
            "email": forms.EmailInput(attrs={"class": _FC}),
            "phone": forms.TextInput(attrs={"class": _FC}),
            "address": forms.TextInput(attrs={"class": _FC}),
            "zip_code": forms.TextInput(attrs={"class": _FC}),
            "stage": forms.Select(attrs={"class": _FS}),
            "quoted_amount": forms.NumberInput(attrs={
                "class": _FC, "step": "0.01", "min": "0", "id": "cl-total",
                "placeholder": "0.00",
            }),
            "tax_amount": forms.NumberInput(attrs={
                "class": _FC, "step": "0.01", "min": "0", "id": "cl-tax",
                "placeholder": "0.00",
            }),
            "commission_rate": forms.NumberInput(attrs={
                "class": _FC, "step": "0.01", "min": "0", "max": "100",
                "id": "cl-rate",
            }),
            "collected_by": forms.Select(attrs={"class": _FS, "id": "cl-collected"}),
            "deposit_percent": forms.NumberInput(attrs={
                "class": _FC, "step": "0.01", "min": "0", "max": "100",
                "id": "cl-deposit",
            }),
            "measure_date": forms.DateInput(attrs={"class": _FC, "type": "date"}),
            "install_date": forms.DateInput(attrs={"class": _FC, "type": "date"}),
            "notes": forms.Textarea(attrs={"class": _FC, "rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["stage"].queryset = self.fields["stage"].queryset.filter(
            is_active=True
        )
        conf = CabinetSettings.get()
        self.fields["commission_rate"].widget.attrs["placeholder"] = (
            f"{conf.commission_rate:g} (board default)"
        )
        self.fields["commission_rate"].help_text = (
            "Leave blank to use the board rate. Set only if this one deal "
            "was agreed at a different split."
        )
        self.fields["tax_amount"].help_text = (
            "Excluded from the commission base."
        )
        self.fields["deposit_percent"].widget.attrs["placeholder"] = (
            f"{conf.default_deposit_percent:g} (board default)"
        )

    def clean(self):
        cleaned = super().clean()
        total = cleaned.get("quoted_amount")
        tax = cleaned.get("tax_amount")
        if total is not None and tax is not None and tax > total:
            self.add_error(
                "tax_amount", "Tax can't be more than the deal total."
            )
        return cleaned


class MemberInviteForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            "class": _FC, "placeholder": "person@example.com",
        }),
    )
    can_edit = forms.BooleanField(
        required=False, initial=True, label="Can edit projects",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class CabinetTodoForm(forms.ModelForm):
    class Meta:
        model = CabinetTodo
        fields = ["title", "due_date"]
        widgets = {
            "title": forms.TextInput(attrs={
                "class": _FC, "placeholder": "Add a task…", "maxlength": "255",
            }),
            "due_date": forms.DateInput(attrs={"class": _FC, "type": "date"}),
        }


# Kept under nginx's default body limit and clearly signposted in the UI.
MAX_ESTIMATE_MB = 20
ALLOWED_ESTIMATE_EXT = {
    ".pdf", ".jpg", ".jpeg", ".png", ".heic", ".webp",
    ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt",
}


class CabinetEstimateForm(forms.ModelForm):
    class Meta:
        model = CabinetEstimate
        fields = ["file", "label"]
        widgets = {
            "file": forms.ClearableFileInput(attrs={"class": _FC}),
            "label": forms.TextInput(attrs={
                "class": _FC, "placeholder": "Optional note, e.g. “Rev 2”",
            }),
        }

    def clean_file(self):
        f = self.cleaned_data["file"]
        name = (getattr(f, "name", "") or "").lower()
        ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
        if ext not in ALLOWED_ESTIMATE_EXT:
            raise forms.ValidationError(
                "That file type isn't accepted. Use a PDF, image, "
                "Word/Excel file, CSV or text file."
            )
        if f.size > MAX_ESTIMATE_MB * 1024 * 1024:
            raise forms.ValidationError(
                f"That file is {f.size / 1024 / 1024:.1f} MB — "
                f"the limit is {MAX_ESTIMATE_MB} MB."
            )
        return f


class CabinetPaymentForm(forms.ModelForm):
    """Register commission received. Defaults to today so the common case is
    one number and a click."""

    class Meta:
        model = CabinetPayment
        fields = ["direction", "amount", "received_on", "method", "reference"]
        widgets = {
            "direction": forms.Select(attrs={"class": _FS}),
            "amount": forms.NumberInput(attrs={
                "class": _FC, "step": "0.01", "min": "0.01", "placeholder": "0.00",
            }),
            "received_on": forms.DateInput(attrs={"class": _FC, "type": "date"}),
            "method": forms.Select(attrs={"class": _FS}),
            "reference": forms.TextInput(attrs={
                "class": _FC, "placeholder": "Cheque no. / ref (optional)",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and not self.initial.get("received_on"):
            self.initial["received_on"] = timezone.localdate()

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("Enter an amount greater than zero.")
        return amount


class CustomerPaymentForm(forms.ModelForm):
    class Meta:
        model = CabinetCustomerPayment
        fields = ["amount", "received_on", "is_deposit", "method", "reference"]
        widgets = {
            "amount": forms.NumberInput(attrs={
                "class": _FC, "step": "0.01", "min": "0.01", "placeholder": "0.00",
            }),
            "received_on": forms.DateInput(attrs={"class": _FC, "type": "date"}),
            "is_deposit": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "method": forms.Select(attrs={"class": _FS}),
            "reference": forms.TextInput(attrs={
                "class": _FC, "placeholder": "Cheque no. / ref (optional)",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and not self.initial.get("received_on"):
            self.initial["received_on"] = timezone.localdate()

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("Enter an amount greater than zero.")
        return amount


class ChangeOrderForm(forms.ModelForm):
    class Meta:
        model = CabinetChangeOrder
        fields = ["description", "amount", "dated"]
        widgets = {
            "description": forms.TextInput(attrs={
                "class": _FC, "placeholder": "e.g. Added two extra cabinets",
            }),
            "amount": forms.NumberInput(attrs={
                "class": _FC, "step": "0.01", "placeholder": "800 or -450",
            }),
            "dated": forms.DateInput(attrs={"class": _FC, "type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and not self.initial.get("dated"):
            self.initial["dated"] = timezone.localdate()

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount == 0:
            raise forms.ValidationError(
                "Use a positive amount to add work, or a negative one to reduce it."
            )
        return amount


class CabinetSettingsForm(forms.ModelForm):
    class Meta:
        model = CabinetSettings
        fields = ["default_collected_by", "commission_basis", "commission_rate",
                  "default_tax_rate", "default_deposit_percent"]
        widgets = {
            "default_collected_by": forms.Select(attrs={"class": _FS}),
            "commission_basis": forms.Select(attrs={"class": _FS, "id": "cl-basis"}),
            "commission_rate": forms.NumberInput(attrs={
                "class": _FC, "step": "0.01", "min": "0", "max": "100",
            }),
            "default_tax_rate": forms.NumberInput(attrs={
                "class": _FC, "step": "0.001", "min": "0", "max": "100",
            }),
            "default_deposit_percent": forms.NumberInput(attrs={
                "class": _FC, "step": "0.01", "min": "0", "max": "100",
            }),
        }


class CabinetStageForm(forms.ModelForm):
    class Meta:
        model = CabinetStage
        fields = ["label", "code", "color", "order", "is_active", "is_won", "is_lost"]
        widgets = {
            "label": forms.TextInput(attrs={"class": _FC}),
            "code": forms.TextInput(attrs={"class": _FC}),
            "color": forms.TextInput(attrs={
                "type": "color", "class": "form-control form-control-color",
                "style": "width:46px; padding:2px;",
            }),
            "order": forms.NumberInput(attrs={"class": _FC, "style": "width:80px"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_won": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_lost": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


CabinetStageFormSet = modelformset_factory(
    CabinetStage, form=CabinetStageForm, extra=0, can_delete=True
)


class NewStageForm(forms.ModelForm):
    class Meta:
        model = CabinetStage
        fields = ["label", "code", "color", "order"]
        widgets = {
            "label": forms.TextInput(attrs={
                "class": _FC, "placeholder": "e.g. Templating",
            }),
            "code": forms.TextInput(attrs={
                "class": _FC, "placeholder": "auto from label if blank",
            }),
            "color": forms.TextInput(attrs={
                "type": "color", "class": "form-control form-control-color",
                "style": "width:46px; padding:2px;",
            }),
            "order": forms.NumberInput(attrs={"class": _FC}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["code"].required = False

    def clean_code(self):
        """Derive a slug from the label when the owner leaves code blank."""
        from django.utils.text import slugify

        code = (self.cleaned_data.get("code") or "").strip()
        if not code:
            code = slugify(self.data.get("label", ""))[:40]
        if not code:
            raise forms.ValidationError("Give the stage a name.")
        if CabinetStage.objects.filter(code=code).exists():
            raise forms.ValidationError(f"A stage with code “{code}” already exists.")
        return code
