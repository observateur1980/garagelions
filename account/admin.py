# account/admin.py

from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.utils.html import format_html

from .models import MyUser, Profile, ProjectManager, Role


# ── Role admin ────────────────────────────────────────────────────────────

@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = (
        'order', 'label', 'code',
        'allows_multiple_locations', 'sees_all_locations',
        'member_count', 'is_protected',
    )
    list_display_links = ('label', 'code')
    list_editable = ('allows_multiple_locations', 'sees_all_locations', 'order')
    list_filter = ('allows_multiple_locations', 'sees_all_locations', 'is_protected')
    search_fields = ('code', 'label', 'description')
    ordering = ('order', 'label')
    fields = (
        'code', 'label', 'description',
        ('allows_multiple_locations', 'sees_all_locations'),
        'order', 'is_protected',
    )

    def get_readonly_fields(self, request, obj=None):
        # Code of seeded roles is referenced by the codebase (see
        # ProjectManager.LOCATION_MANAGER etc.) — renaming would break
        # those checks, so lock it.
        if obj and obj.is_protected:
            return ('code', 'is_protected')
        return ()

    def has_delete_permission(self, request, obj=None):
        if obj and obj.is_protected:
            return False
        return super().has_delete_permission(request, obj)

    def delete_queryset(self, request, queryset):
        protected = queryset.filter(is_protected=True)
        if protected.exists():
            messages.error(
                request,
                f"Skipped {protected.count()} protected role(s); they're "
                "referenced in code and cannot be deleted.",
            )
        queryset.filter(is_protected=False).delete()

    def member_count(self, obj):
        return ProjectManager.objects.filter(role=obj.code).count()
    member_count.short_description = '# Users'


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


def _role_choices(current_code=None):
    """Role.code/label pairs, plus a fallback for the row's stored code so
    we never lose a custom or stale value during a save.
    Same pattern as LeadAdmin's _lead_status_choices in home/admin.py.
    """
    choices = list(Role.objects.values_list('code', 'label'))
    if current_code and not any(c == current_code for c, _ in choices):
        choices.append((current_code, current_code.replace('_', ' ').title()))
    return choices


class ProjectManagerForm(forms.ModelForm):
    """Form used in admin for ProjectManager — keeps the role dropdown in
    sync with the Role table (and tolerates legacy/orphan codes)."""

    class Meta:
        model = ProjectManager
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'role' in self.fields:
            current = self.instance.role if self.instance and self.instance.pk else None
            self.fields['role'] = forms.ChoiceField(
                choices=_role_choices(current_code=current),
                label=self.fields['role'].label,
                required=True,
            )


class ProjectManagerInline(admin.StackedInline):
    model = ProjectManager
    form = ProjectManagerForm
    can_delete = False
    verbose_name = 'Business Role'
    verbose_name_plural = 'Business Role'
    fields = (
        ('role', 'status', 'employment_type'),
        ('sales_point', 'manager'),
        'extra_sales_points',
        ('base_salary', 'commission_rate', 'draw_amount'),
        ('start_date', 'end_date'),
        'territory_notes',
        'internal_notes',
    )
    filter_horizontal = ('extra_sales_points',)
    extra = 0


# ── MyUser admin ──────────────────────────────────────────────────────────

@admin.register(MyUser)
class MyUserAdmin(BaseUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    inlines = [ProfileInline, ProjectManagerInline]

    list_display = (
        'username', 'email',
        'get_full_name', 'get_role', 'get_locations',
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

    def get_locations(self, obj):
        try:
            pm = obj.project_manager
        except ProjectManager.DoesNotExist:
            return '—'
        connections = pm.connected_sales_points
        if pm.sees_all_locations:
            from home.models import SalesPoint
            total = SalesPoint.objects.filter(is_active=True).count()
            direct = len(connections)
            if direct:
                names = ', '.join(sp.name for sp, _ in connections)
                return format_html(
                    '<b>All ({})</b> — directly tied to {}: {}',
                    total, direct, names,
                )
            return format_html('<b>All ({})</b> — role sees everything', total)
        if not connections:
            return '—'
        return format_html(
            '<b>{}</b> — {}',
            len(connections),
            ', '.join(sp.name for sp, _ in connections),
        )
    get_locations.short_description = 'Locations managed'

    def get_status(self, obj):
        try:
            return obj.project_manager.get_status_display()
        except ProjectManager.DoesNotExist:
            return '—'
    get_status.short_description = 'Status'


# ── Standalone ProjectManager admin ──────────────────────────────────────────

@admin.register(ProjectManager)
class ProjectManagerAdmin(admin.ModelAdmin):
    form = ProjectManagerForm
    list_display = (
        'get_full_name', 'get_email',
        'get_role_label', 'status', 'employment_type',
        'get_locations', 'manager',
        'commission_rate', 'start_date',
    )
    list_filter = ('role', 'status', 'employment_type', 'sales_point')
    search_fields = (
        'user__username', 'user__email',
        'user__profile__first_name', 'user__profile__last_name',
    )
    readonly_fields = ('created_at', 'updated_at', 'managed_locations_summary')
    raw_id_fields = ('user',)
    filter_horizontal = ('extra_sales_points',)

    fieldsets = (
        ('User', {'fields': ('user',)}),
        ('Role & Status', {
            'fields': (
                ('role', 'status', 'employment_type'),
                ('sales_point', 'manager'),
                'extra_sales_points',
                'managed_locations_summary',
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

    def get_role_label(self, obj):
        return obj.get_role_display()
    get_role_label.short_description = 'Role'
    get_role_label.admin_order_field = 'role'

    def get_locations(self, obj):
        connections = obj.connected_sales_points
        if obj.sees_all_locations:
            from home.models import SalesPoint
            total = SalesPoint.objects.filter(is_active=True).count()
            direct = len(connections)
            if direct:
                names = ', '.join(sp.name for sp, _ in connections)
                return format_html(
                    '<b>All ({})</b> — directly tied to {}: {}',
                    total, direct, names,
                )
            return format_html('<b>All ({})</b> — role sees everything', total)
        if not connections:
            return '—'
        return format_html(
            '<b>{}</b> — {}',
            len(connections),
            ', '.join(sp.name for sp, _ in connections),
        )
    get_locations.short_description = 'Locations managed'

    def managed_locations_summary(self, obj):
        if not obj or not obj.pk:
            return '—'

        from django.utils.html import format_html_join

        connections = obj.connected_sales_points

        # Build the explicit-connection list with provenance tags.
        if connections:
            rows = format_html_join(
                '',
                '<li><b>{}</b> <span style="color:#6b7280;">— {}</span></li>',
                ((sp.name, ', '.join(tags)) for sp, tags in connections),
            )
            connection_html = format_html(
                '<b>{} location(s) directly tied to this user:</b>'
                '<ul style="margin-top:6px;">{}</ul>',
                len(connections), rows,
            )
        else:
            connection_html = format_html(
                '<i>No direct connections yet. Set a primary sales point above'
                '{}, or assign this user as <code>assigned_user</code> on a '
                'SalesPoint.</i>',
                ', add extras,' if obj.allows_multiple_locations else '',
            )

        # Then the role-visibility line.
        if obj.sees_all_locations:
            from home.models import SalesPoint
            total = SalesPoint.objects.filter(is_active=True).count()
            visibility_html = format_html(
                '<p style="margin-top:10px;"><b>Role visibility:</b> sees '
                'all <b>{}</b> active sales points (role: {}).</p>',
                total, obj.get_role_display(),
            )
        elif obj.allows_multiple_locations:
            visibility_html = format_html(
                '<p style="margin-top:10px;"><b>Role visibility:</b> primary + '
                'extras (role: {} — multi-location).</p>',
                obj.get_role_display(),
            )
        else:
            visibility_html = format_html(
                '<p style="margin-top:10px;"><b>Role visibility:</b> primary '
                'only (role: {} — single-location).</p>',
                obj.get_role_display(),
            )

        legend_html = format_html(
            '<p style="margin-top:8px;color:#6b7280;font-size:11px;">'
            'Tags: <code>primary</code> = this PM record\'s primary sales '
            'point · <code>extra</code> = in extras above · '
            '<code>assigned_user</code> = listed as point of contact on '
            'the SalesPoint admin page.</p>'
        )

        return format_html('{}{}{}', connection_html, visibility_html, legend_html)
    managed_locations_summary.short_description = 'Managed locations'