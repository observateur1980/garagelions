from django import forms
from django.core.exceptions import ValidationError
from .models import LeadModel, LeadStatus


def _db_status_choices(current_code=None):
    """
    Return the status choices currently allowed by the LeadStatus table.

    If `current_code` is provided and isn't already in the table (e.g. an
    existing lead carries an old status that was later removed), it is
    appended so the ModelForm doesn't reject the bound value.
    """
    choices = list(LeadStatus.objects.values_list("code", "label"))
    if current_code and not any(c == current_code for c, _ in choices):
        choices.append((current_code, current_code.replace("_", " ").title()))
    return choices

LEAD_MAX_FILES = 10
LEAD_MAX_FILE_SIZE_MB = 2048
LEAD_MAX_FILE_SIZE = LEAD_MAX_FILE_SIZE_MB * 1024 * 1024
LEAD_MAX_TOTAL_SIZE_MB = 6144
LEAD_MAX_TOTAL_SIZE = LEAD_MAX_TOTAL_SIZE_MB * 1024 * 1024


class MultipleFileField(forms.FileField):
    def clean(self, data, initial=None):
        if data in (None, "", [], ()):
            return [] if not self.required else super().clean(None, initial)

        if isinstance(data, (list, tuple)):
            files = [f for f in data if f not in (None, "", False)]
            if not files:
                return [] if not self.required else super().clean(None, initial)
            cleaned = []
            for f in files:
                cleaned.append(super().clean(f, initial))
            return cleaned

        return [super().clean(data, initial)]


class LeadForm(forms.ModelForm):
    class MultipleFileInput(forms.ClearableFileInput):
        allow_multiple_selected = True

    attachments = MultipleFileField(
        required=False,
        widget=MultipleFileInput(attrs={
            "multiple": True,
            "accept": "image/*,video/*",
        }),
        help_text=f"Up to {LEAD_MAX_FILES} files. Max {LEAD_MAX_FILE_SIZE_MB}MB each (max {LEAD_MAX_TOTAL_SIZE_MB}MB total).",
    )

    class Meta:
        model = LeadModel
        fields = ["first_name", "last_name", "email", "phone", "zip_code", "consultation_types", "message"]
        widgets = {
            "consultation_types": forms.CheckboxSelectMultiple,
            "message": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["first_name"].widget.attrs.update({
            "class": "form-control",

        })

        self.fields["last_name"].widget.attrs.update({
            "class": "form-control",

        })
        self.fields["email"].widget.attrs.update({
            "class": "form-control",

        })
        self.fields["phone"].widget.attrs.update({
            "class": "form-control",

        })
        self.fields["zip_code"].widget.attrs.update({
            "class": "form-control",

        })
        self.fields["message"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Tell us about your garage project",
        })

    def clean_zip_code(self):
        zip_code = (self.cleaned_data.get("zip_code") or "").strip()
        allowed = "".join(ch for ch in zip_code if ch.isdigit() or ch == "-")
        if len(allowed) < 5:
            raise ValidationError("Please enter a valid ZIP code.")
        return allowed

    def clean_attachments(self):
        files = self.files.getlist("attachments")
        if not files:
            return []

        if len(files) > LEAD_MAX_FILES:
            raise ValidationError(f"Please upload up to {LEAD_MAX_FILES} files.")

        total_size = sum(getattr(f, "size", 0) or 0 for f in files)
        if total_size > LEAD_MAX_TOTAL_SIZE:
            raise ValidationError(
                f"Total upload size exceeds {LEAD_MAX_TOTAL_SIZE_MB}MB limit. "
                f"Please upload fewer files or shorter videos."
            )

        for f in files:
            if getattr(f, "size", 0) > LEAD_MAX_FILE_SIZE:
                raise ValidationError(f"{f.name}: exceeds {LEAD_MAX_FILE_SIZE_MB}MB limit.")

            ctype = getattr(f, "content_type", "") or ""
            if ctype and not (ctype.startswith("image/") or ctype.startswith("video/")):
                raise ValidationError(f"{f.name}: only image/video files are allowed.")

        return files





# -----------------------------------------------------------------------
# ADD this class to the bottom of home/forms.py
# -----------------------------------------------------------------------





class LeadUpdateForm(forms.ModelForm):
    """Used by salespeople to update a lead's status and add internal notes."""

    class Meta:
        model = LeadModel
        fields = ['status', 'internal_notes']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-control'}),
            'internal_notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Internal notes — not visible to the customer.',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current = self.instance.status if self.instance and self.instance.pk else None
        self.fields['status'].choices = _db_status_choices(current_code=current)










# ── ADD to the bottom of home/forms.py ──────────────────────────────────────

class ManualLeadForm(forms.ModelForm):
    """
    Used by salespeople to manually add a lead from inside the CRM.
    Includes all LeadModel fields plus explicit assignment controls.
    """

    class Meta:
        model = LeadModel
        fields = [
            'first_name', 'last_name', 'email', 'phone', 'address', 'zip_code',
            'consultation_types', 'message',
            'sales_point', 'service_city', 'assigned_user',
            'status', 'internal_notes', 'source_page',
        ]
        widgets = {
            'first_name':         forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First name'}),
            'last_name':          forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last name'}),
            'email':              forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'email@example.com'}),
            'phone':              forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone number'}),
            'address':            forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Street address'}),
            'zip_code':           forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ZIP code'}),
            'consultation_types': forms.CheckboxSelectMultiple(),
            'message':            forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Notes about the lead…'}),
            'sales_point':        forms.Select(attrs={'class': 'form-control'}),
            'service_city':       forms.Select(attrs={'class': 'form-control'}),
            'assigned_user':      forms.Select(attrs={'class': 'form-control'}),
            'status':             forms.Select(attrs={'class': 'form-control'}),
            'internal_notes':     forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Internal notes (not visible to customer)'}),
            'source_page':        forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Phone call, Walk-in, Referral'}),
        }
        labels = {
            'source_page': 'Source / How did they find us?',
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Status choices come from the DB-managed LeadStatus table
        current = self.instance.status if self.instance and self.instance.pk else None
        self.fields['status'].choices = _db_status_choices(current_code=current)

        # Make assignment fields optional
        self.fields['sales_point'].required = False
        self.fields['service_city'].required = False
        self.fields['assigned_user'].required = False
        self.fields['internal_notes'].required = False
        self.fields['source_page'].required = False
        self.fields['message'].required = False
        self.fields['consultation_types'].required = False

        # Add blank option to dropdowns
        self.fields['sales_point'].empty_label = '— Select location —'
        self.fields['service_city'].empty_label = '— Select city —'
        self.fields['assigned_user'].empty_label = '— Unassigned —'

        # If a regular salesperson (not staff), lock sales_point to their own location
        if user and not user.is_staff and not user.is_superuser:
            try:
                sp = user.project_manager.sales_point
                if sp:
                    self.fields['sales_point'].initial = sp
                    self.fields['sales_point'].queryset = \
                        self.fields['sales_point'].queryset.filter(pk=sp.pk)
                    self.fields['sales_point'].widget.attrs['disabled'] = True
                    self.fields['service_city'].queryset = \
                        self.fields['service_city'].queryset.filter(sales_point=sp)
                    self.fields['assigned_user'].queryset = \
                        self.fields['assigned_user'].queryset.filter(
                            project_manager__sales_point=sp
                        )
            except Exception:
                pass