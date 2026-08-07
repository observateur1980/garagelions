from django import forms

from .models import CabinetProject

_FC = "form-control"
_FS = "form-select"


class CabinetProjectForm(forms.ModelForm):
    class Meta:
        model = CabinetProject
        fields = [
            "title", "customer_name", "email", "phone", "address", "zip_code",
            "stage", "quoted_amount", "linear_feet", "finish",
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
            "quoted_amount": forms.NumberInput(attrs={"class": _FC, "step": "0.01"}),
            "linear_feet": forms.NumberInput(attrs={"class": _FC, "step": "0.01"}),
            "finish": forms.TextInput(attrs={"class": _FC}),
            "measure_date": forms.DateInput(attrs={"class": _FC, "type": "date"}),
            "install_date": forms.DateInput(attrs={"class": _FC, "type": "date"}),
            "notes": forms.Textarea(attrs={"class": _FC, "rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["stage"].queryset = self.fields["stage"].queryset.filter(
            is_active=True
        )


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
