# account/forms.py

from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q

from .models import Profile, ProjectManager

User = get_user_model()

_FC = 'form-control'
_CC = 'form-check-input'


class UserLoginForm(forms.Form):
    query = forms.CharField(
        label='Email or Username',
        widget=forms.TextInput(attrs={
            'id': 'login-query',
            'placeholder': 'Email or username',
            'class': _FC,
            'autocomplete': 'username',
        }),
    )
    password = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={
            'id': 'password',
            'placeholder': 'Password',
            'class': _FC,
            'autocomplete': 'current-password',
        }),
    )

    def clean(self):
        cleaned = super().clean()
        query = (cleaned.get('query') or '').strip()
        password = cleaned.get('password')

        if not query or not password:
            raise forms.ValidationError('Please enter your email/username and password.')

        qs = User.objects.filter(
            Q(username__iexact=query) | Q(email__iexact=query)
        ).distinct()

        if qs.count() != 1:
            raise forms.ValidationError('Invalid credentials.')

        user = qs.first()
        if not user.check_password(password):
            raise forms.ValidationError('Invalid credentials.')
        if not user.is_active:
            raise forms.ValidationError('This account is inactive.')

        cleaned['user_obj'] = user
        return cleaned


class ProfileForm(forms.ModelForm):
    """Salesperson edits their own personal info."""

    TIMEZONE_CHOICES = [
        ('America/New_York',    'Eastern — New York'),
        ('America/Chicago',     'Central — Chicago'),
        ('America/Denver',      'Mountain — Denver'),
        ('America/Phoenix',     'Mountain no-DST — Phoenix'),
        ('America/Los_Angeles', 'Pacific — Los Angeles'),
        ('America/Anchorage',   'Alaska — Anchorage'),
        ('Pacific/Honolulu',    'Hawaii — Honolulu'),
    ]

    timezone = forms.ChoiceField(
        choices=TIMEZONE_CHOICES,
        widget=forms.Select(attrs={'class': _FC}),
        required=False,
    )

    class Meta:
        model = Profile
        fields = [
            'first_name', 'last_name', 'photo', 'bio',
            'phone', 'mobile', 'direct_email',
            'city', 'state', 'timezone',
            'linkedin_url', 'calendly_url',
            'notify_new_lead_email', 'notify_new_lead_sms',
            'emergency_contact_name', 'emergency_contact_phone',
        ]
        widgets = {
            'first_name':             forms.TextInput(attrs={'class': _FC, 'placeholder': 'First name'}),
            'last_name':              forms.TextInput(attrs={'class': _FC, 'placeholder': 'Last name'}),
            'bio':                    forms.Textarea(attrs={'class': _FC, 'rows': 3, 'placeholder': 'Short bio…'}),
            'phone':                  forms.TextInput(attrs={'class': _FC, 'placeholder': 'Office phone'}),
            'mobile':                 forms.TextInput(attrs={'class': _FC, 'placeholder': 'Mobile / cell'}),
            'direct_email':           forms.EmailInput(attrs={'class': _FC, 'placeholder': 'your@email.com'}),
            'city':                   forms.TextInput(attrs={'class': _FC, 'placeholder': 'City'}),
            'state':                  forms.TextInput(attrs={'class': _FC, 'placeholder': 'State'}),
            'linkedin_url':           forms.URLInput(attrs={'class': _FC, 'placeholder': 'https://linkedin.com/in/…'}),
            'calendly_url':           forms.URLInput(attrs={'class': _FC, 'placeholder': 'https://calendly.com/…'}),
            'notify_new_lead_email':  forms.CheckboxInput(attrs={'class': _CC}),
            'notify_new_lead_sms':    forms.CheckboxInput(attrs={'class': _CC}),
            'emergency_contact_name': forms.TextInput(attrs={'class': _FC, 'placeholder': 'Full name'}),
            'emergency_contact_phone':forms.TextInput(attrs={'class': _FC, 'placeholder': 'Phone number'}),
        }
        labels = {
            'notify_new_lead_email': 'Email me when a new lead is assigned',
            'notify_new_lead_sms':   'SMS me when a new lead is assigned (requires SMS setup)',
        }


class ProjectManagerAdminForm(forms.ModelForm):
    """
    Used by admins only to manage the ProjectManager record.
    Project managers cannot edit their own compensation or role.
    """

    class Meta:
        model = ProjectManager
        fields = [
            'user', 'sales_point', 'manager',
            'role', 'status', 'employment_type',
            'base_salary', 'commission_rate', 'draw_amount',
            'start_date', 'end_date',
            'territory_notes', 'internal_notes',
        ]
        widgets = {
            'role':             forms.Select(attrs={'class': _FC}),
            'status':           forms.Select(attrs={'class': _FC}),
            'employment_type':  forms.Select(attrs={'class': _FC}),
            'base_salary':      forms.NumberInput(attrs={'class': _FC, 'placeholder': '0.00'}),
            'commission_rate':  forms.NumberInput(attrs={'class': _FC, 'placeholder': '0.00'}),
            'draw_amount':      forms.NumberInput(attrs={'class': _FC, 'placeholder': '0.00'}),
            'start_date':       forms.DateInput(attrs={'class': _FC, 'type': 'date'}),
            'end_date':         forms.DateInput(attrs={'class': _FC, 'type': 'date'}),
            'territory_notes':  forms.Textarea(attrs={'class': _FC, 'rows': 3}),
            'internal_notes':   forms.Textarea(attrs={'class': _FC, 'rows': 3}),
        }


class AdminSetPasswordForm(forms.Form):
    """Staff-only form to set a new password for any user (no old password required)."""

    new_password1 = forms.CharField(
        label='New password',
        widget=forms.PasswordInput(attrs={'class': _FC, 'autocomplete': 'new-password'}),
    )
    new_password2 = forms.CharField(
        label='Confirm new password',
        widget=forms.PasswordInput(attrs={'class': _FC, 'autocomplete': 'new-password'}),
    )

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('new_password1')
        p2 = cleaned.get('new_password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('The two passwords do not match.')
        return cleaned