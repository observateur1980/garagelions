# forms.py
from django import forms
from django.core.exceptions import ValidationError

from .models import LeadModel


# --- Upload limits (tweak if you want) ---
LEAD_MAX_FILES = 10
LEAD_MAX_FILE_SIZE_MB = 2048  # allow big phone videos
LEAD_MAX_FILE_SIZE = LEAD_MAX_FILE_SIZE_MB * 1024 * 1024
LEAD_MAX_TOTAL_SIZE_MB = 6144  # total per submission
LEAD_MAX_TOTAL_SIZE = LEAD_MAX_TOTAL_SIZE_MB * 1024 * 1024


class MultipleFileField(forms.FileField):
    """A FileField that can handle multiple uploaded files."""

    def clean(self, data, initial=None):
        # When no file is selected, browsers may send None/''.
        if data in (None, "", [], ()):
            return [] if not self.required else super().clean(None, initial)

        # With multiple=True, Django's widget provides a list of UploadedFile objects.
        if isinstance(data, (list, tuple)):
            files = [f for f in data if f not in (None, "", False)]
            if not files:
                return [] if not self.required else super().clean(None, initial)
            # Run base validation on each file (content_type/size is validated later).
            cleaned = []
            for f in files:
                cleaned.append(super().clean(f, initial))
            return cleaned

        # Fallback: single file
        return [super().clean(data, initial)]


class LeadForm(forms.ModelForm):
    class MultipleFileInput(forms.ClearableFileInput):
        """Enable <input type=file multiple> for Django."""
        allow_multiple_selected = True

    # Optional attachments (photos/videos)
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
        fields = ['name', 'email', 'phone', 'consultation_types', 'message']
        widgets = {
            'consultation_types': forms.CheckboxSelectMultiple,
            'message': forms.Textarea(attrs={'rows': 4}),
        }

    def clean_attachments(self):
        """Validate number/size/type of uploaded files."""
        files = self.files.getlist("attachments")
        if not files:
            return []

        if len(files) > LEAD_MAX_FILES:
            raise ValidationError(f"Please upload up to {LEAD_MAX_FILES} files.")

        total_size = sum(getattr(f, 'size', 0) or 0 for f in files)
        if total_size > LEAD_MAX_TOTAL_SIZE:
            raise ValidationError(
                f"Total upload size exceeds {LEAD_MAX_TOTAL_SIZE_MB}MB limit. "
                f"Please upload fewer files or shorter videos."
            )

        for f in files:
            # Size limit
            if getattr(f, "size", 0) > LEAD_MAX_FILE_SIZE:
                raise ValidationError(
                    f"{f.name}: exceeds {LEAD_MAX_FILE_SIZE_MB}MB limit."
                )

            # Type check (best-effort)
            ctype = getattr(f, "content_type", "") or ""
            if ctype and not (ctype.startswith("image/") or ctype.startswith("video/")):
                raise ValidationError(
                    f"{f.name}: only image/video files are allowed."
                )

        return files
