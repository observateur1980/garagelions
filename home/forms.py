from django import forms
from django.core.exceptions import ValidationError
from .models import LeadModel

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