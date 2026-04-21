# account/views.py

from django.contrib import messages
from django.contrib.auth import login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordChangeView, PasswordChangeDoneView
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render, redirect
from django.urls import reverse, reverse_lazy

from .forms import UserLoginForm, ProfileForm, AdminSetPasswordForm
from .models import ProjectManager

User = get_user_model()


def _dashboard_url(user):
    """Return the panel dashboard URL."""
    return reverse('panel:dashboard')


def user_login(request):
    if request.user.is_authenticated:
        return HttpResponseRedirect(_dashboard_url(request.user))

    form = UserLoginForm(request.POST or None)
    if form.is_valid():
        user = form.cleaned_data['user_obj']
        login(request, user)
        return HttpResponseRedirect(_dashboard_url(user))

    return render(request, 'account/login.html', {'form': form})


def user_logout(request):
    logout(request)
    return HttpResponseRedirect(reverse('account:login'))


@login_required
def profile_edit(request):
    profile = request.user.profile

    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your profile has been updated.')
            return redirect('account:profile_edit')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ProfileForm(instance=profile)

    # Try to attach project manager record if it exists
    project_manager = None
    try:
        project_manager = request.user.project_manager
    except ProjectManager.DoesNotExist:
        pass

    return render(request, 'account/profile_edit.html', {
        'form': form,
        'profile': profile,
        'project_manager': project_manager,
    })


class SalesPasswordChangeView(PasswordChangeView):
    template_name = 'account/password_change.html'
    success_url = reverse_lazy('account:password_change_done')


class SalesPasswordChangeDoneView(PasswordChangeDoneView):
    template_name = 'account/password_change_done.html'


password_change_view = login_required(SalesPasswordChangeView.as_view())
password_change_done_view = login_required(SalesPasswordChangeDoneView.as_view())


@login_required
def admin_user_list(request):
    """Staff-only: list all users and project managers for password management."""
    if not request.user.is_staff:
        raise Http404

    all_users = User.objects.select_related('profile').order_by('profile__last_name', 'profile__first_name', 'username')
    project_managers = ProjectManager.objects.select_related('user', 'user__profile', 'sales_point').order_by(
        'user__profile__last_name', 'user__profile__first_name'
    )

    return render(request, 'account/admin_user_list.html', {
        'all_users': all_users,
        'project_managers': project_managers,
    })


@login_required
def admin_change_user_password(request, user_id):
    """Staff-only: set a new password for any user."""
    if not request.user.is_staff:
        raise Http404

    target = User.objects.select_related('profile').filter(pk=user_id).first()
    if not target:
        raise Http404

    form = AdminSetPasswordForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        target.set_password(form.cleaned_data['new_password1'])
        target.save()
        messages.success(request, f'Password updated for {target.get_full_name() or target.username}.')
        return redirect('account:admin_user_list')

    return render(request, 'account/admin_change_password.html', {
        'form': form,
        'target': target,
    })