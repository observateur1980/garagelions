# account/views.py

from django.contrib import messages
from django.contrib.auth import login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordChangeView, PasswordChangeDoneView
from django.http import HttpResponseRedirect
from django.shortcuts import render, redirect
from django.urls import reverse, reverse_lazy

from .forms import UserLoginForm, ProfileForm
from .models import Salesperson

User = get_user_model()


def _dashboard_url(user):
    """Return the correct dashboard URL based on the user's role."""
    try:
        role = user.salesperson.role
        if role == Salesperson.TERRITORY_MANAGER:
            return reverse('sales_dashboard_territory')
        if role == Salesperson.LOCATION_MANAGER:
            return reverse('sales_dashboard_manager')
    except Salesperson.DoesNotExist:
        pass
    return reverse('sales_dashboard')


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

    # Try to attach salesperson record if it exists
    salesperson = None
    try:
        salesperson = request.user.salesperson
    except Salesperson.DoesNotExist:
        pass

    return render(request, 'account/profile_edit.html', {
        'form': form,
        'profile': profile,
        'salesperson': salesperson,
    })


class SalesPasswordChangeView(PasswordChangeView):
    template_name = 'account/password_change.html'
    success_url = reverse_lazy('account:password_change_done')


class SalesPasswordChangeDoneView(PasswordChangeDoneView):
    template_name = 'account/password_change_done.html'


password_change_view = login_required(SalesPasswordChangeView.as_view())
password_change_done_view = login_required(SalesPasswordChangeDoneView.as_view())