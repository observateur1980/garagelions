from django.contrib.auth import login, get_user_model, logout
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse

from .forms import UserLoginForm

User = get_user_model()


def user_login(request, *args, **kwargs):
    form = UserLoginForm(request.POST or None)
    if form.is_valid():
        user_obj = form.cleaned_data.get('user_obj')
        login(request, user_obj)
        return HttpResponseRedirect(reverse('home'))

    return render(request, 'account/login.html',
                  {'form': form, 'menu': "login"}
                  )


def user_logout(request):
    logout(request)
    return HttpResponseRedirect(reverse('account:login'))
