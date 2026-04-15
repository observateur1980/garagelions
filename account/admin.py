# account/admin.py

from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField

from .models import MyUser, Profile, ProjectManager


# ── Auth forms ────────────────────────────────────────────────────────────

class UserCreationForm(forms.ModelForm):
    password1 = forms.CharField(label='Password', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirm password', widget=forms.PasswordInput)

    class Meta:
        model = MyUser
        fields = ('username', 'email')

    def clean_password2(self):
        p1, p2 = self.cleaned_data.get('password1'), self.cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Passwords don't match.")
        return p2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


class UserChangeForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField(
        help_text='Raw passwords are not stored. <a href="../password/">Change it here</a>.',
    )

    class Meta:
        model = MyUser
        fields = ('username', 'email', 'password', 'is_active', 'is_staff', 'is_superuser')

    def clean_password(self):
        return self.initial.get('password')


# ── Inlines ───────────────────────────────────────────────────────────────

class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name = 'Profile'
    verbose_name_plural = 'Profile'
    fields = (
        ('first_name', 'last_name'),
        'photo', 'bio',
        ('phone', 'mobile'),
        'direct_email',
        ('city', 'state', 'timezone'),
        'linkedin_url', 'calendly_url',
        ('notify_new_lead_email', 'notify_new_lead_sms'),
        ('emergency_contact_name', 'emergency_contact_phone'),
    )


class ProjectManagerInline(admin.StackedInline):
    model = ProjectManager
    can_delete = False
    verbose_name = 'Business Role'
    verbose_name_plural = 'Business Role'
    fields = (
        ('role', 'status', 'employment_type'),
        ('sales_point', 'manager'),
        ('base_salary', 'commission_rate', 'draw_amount'),
        ('start_date', 'end_date'),
        'territory_notes',
        'internal_notes',
    )
    extra = 0


# ── MyUser admin ──────────────────────────────────────────────────────────

@admin.register(MyUser)
class MyUserAdmin(BaseUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    inlines = [ProfileInline, ProjectManagerInline]

    list_display = (
        'username', 'email',
        'get_full_name', 'get_role', 'get_location',
        'get_status', 'is_staff', 'is_active',
    )
    list_filter = (
        'is_staff', 'is_active',
        'project_manager__role', 'project_manager__status',
        'project_manager__sales_point',
    )
    search_fields = (
        'username', 'email',
        'profile__first_name', 'profile__last_name',
        'profile__phone', 'profile__mobile',
    )
    ordering = ('username',)
    filter_horizontal = ('groups', 'user_permissions')

    fieldsets = (
        (None, {'fields': ('username', 'email', 'password')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2', 'is_staff', 'is_active'),
        }),
    )

    def save_related(self, request, form, formsets, change):
        # On both add AND edit: if a ProfileInline form has no pk yet,
        # check whether a Profile already exists for this user and reuse it
        # (UPDATE) instead of trying to INSERT a duplicate (IntegrityError).
        for formset in formsets:
            if formset.model == Profile:
                for f in formset.forms:
                    if not f.instance.pk:
                        try:
                            f.instance = Profile.objects.get(user=form.instance)
                        except Profile.DoesNotExist:
                            pass
        super().save_related(request, form, formsets, change)

    def get_full_name(self, obj):
        try:
            return obj.profile.full_name
        except Profile.DoesNotExist:
            return '—'
    get_full_name.short_description = 'Full Name'

    def get_role(self, obj):
        try:
            return obj.project_manager.get_role_display()
        except ProjectManager.DoesNotExist:
            return '—'
    get_role.short_description = 'Role'

    def get_location(self, obj):
        try:
            sp = obj.project_manager.sales_point
            return sp.name if sp else '—'
        except ProjectManager.DoesNotExist:
            return '—'
    get_location.short_description = 'Location'

    def get_status(self, obj):
        try:
            return obj.project_manager.get_status_display()
        except ProjectManager.DoesNotExist:
            return '—'
    get_status.short_description = 'Status'


# ── Standalone ProjectManager admin ──────────────────────────────────────────

@admin.register(ProjectManager)
class ProjectManagerAdmin(admin.ModelAdmin):
    list_display = (
        'get_full_name', 'get_email',
        'role', 'status', 'employment_type',
        'sales_point', 'manager',
        'commission_rate', 'start_date',
    )
    list_filter = ('role', 'status', 'employment_type', 'sales_point')
    search_fields = (
        'user__username', 'user__email',
        'user__profile__first_name', 'user__profile__last_name',
    )
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('user',)
    filter_horizontal = ('extra_sales_points',)

    fieldsets = (
        ('User', {'fields': ('user',)}),
        ('Role & Status', {
            'fields': (
                ('role', 'status', 'employment_type'),
                ('sales_point', 'manager'),
                'extra_sales_points',
            )
        }),
        ('Compensation', {
            'fields': (
                ('base_salary', 'commission_rate', 'draw_amount'),
            )
        }),
        ('Dates', {
            'fields': (('start_date', 'end_date'),)
        }),
        ('Territory & Notes', {
            'fields': ('territory_notes', 'internal_notes'),
        }),
        ('Audit', {
            'fields': (('created_at', 'updated_at'),),
            'classes': ('collapse',),
        }),
    )

    def get_full_name(self, obj):
        return obj.user.get_full_name()
    get_full_name.short_description = 'Name'
    get_full_name.admin_order_field = 'user__profile__last_name'

    def get_email(self, obj):
        return obj.user.email
    get_email.short_description = 'Email'