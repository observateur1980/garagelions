from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()


class UserLoginForm(forms.Form):
    query = forms.CharField(
        label="Email or Username",
        widget=forms.TextInput(
            attrs={
                "id": "login-query",
                "placeholder": "Enter your email or username",
                "class": "form-control",
                "autocomplete": "username",
            }
        ),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(
            attrs={
                "id": "password",
                "placeholder": "Enter your password",
                "class": "form-control",
                "autocomplete": "current-password",
            }
        ),
    )

    def clean(self):
        cleaned_data = super().clean()
        query = (cleaned_data.get("query") or "").strip()
        password = cleaned_data.get("password")

        if not query or not password:
            raise forms.ValidationError("Please enter your email or username and password.")

        user_qs = User.objects.filter(
            Q(username__iexact=query) | Q(email__iexact=query)
        ).distinct()

        if user_qs.count() != 1:
            raise forms.ValidationError("Invalid login credentials.")

        user_obj = user_qs.first()

        if not user_obj.check_password(password):
            raise forms.ValidationError("Invalid login credentials.")

        if not user_obj.is_active:
            raise forms.ValidationError("This account is inactive.")

        cleaned_data["user_obj"] = user_obj
        return cleaned_data
