from django import forms
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.contrib.auth import get_user_model, authenticate
from .models import MyUser
from django.core.validators import RegexValidator

User = get_user_model()

from .models import USERNAME_REGEX
from django.db.models import Q


class UserLoginForm(forms.Form):
    query = forms.CharField(
        widget=forms.TextInput(attrs={'id': 'contact-email', 'name': 'contact-email',
                                      'placeholder': 'Enter email', 'class': 'form-control', 'type': 'email'}))

    password = forms.CharField(widget=forms.PasswordInput(attrs={'id': 'password', 'name': 'password',
                                                                 'placeholder': 'Enter password',
                                                                 'class': 'form-control', 'type': 'password'}))

    def clean(self, *args, **kwargs):
        query = self.cleaned_data.get('query')
        password = self.cleaned_data.get('password')

        user_qs_final = User.objects.filter(

            Q(username__iexact=query) |
            Q(email__iexact=query)

        ).distinct()

        if not user_qs_final.exists() and user_qs_final.count() != 1:
            raise forms.ValidationError('Invalid credantials - user not exsist')

        user_obj = user_qs_final.first()
        if not user_obj.check_password(password):
            raise forms.ValidationError('Invalid credantials - password invalid')

        if not user_obj.is_active:
            raise forms.ValidationError('Inactive user')

        self.cleaned_data['user_obj'] = user_obj
        return super(UserLoginForm, self).clean(*args, **kwargs)


