from django.contrib.auth import login, get_user_model, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordChangeView, PasswordChangeDoneView
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse, reverse_lazy

from .forms import UserLoginForm

User = get_user_model()


def user_login(request, *args, **kwargs):
    if request.user.is_authenticated:
        return HttpResponseRedirect(reverse("sales_dashboard"))

    form = UserLoginForm(request.POST or None)
    if form.is_valid():
        user_obj = form.cleaned_data.get("user_obj")
        login(request, user_obj)
        return HttpResponseRedirect(reverse("sales_dashboard"))

    return render(request, "account/login.html", {"form": form})


def user_logout(request):
    logout(request)
    return HttpResponseRedirect(reverse("account:login"))


class SalesPasswordChangeView(PasswordChangeView):
    template_name = "account/password_change.html"
    success_url = reverse_lazy("account:password_change_done")


class SalesPasswordChangeDoneView(PasswordChangeDoneView):
    template_name = "account/password_change_done.html"


password_change_view = login_required(SalesPasswordChangeView.as_view())
password_change_done_view = login_required(SalesPasswordChangeDoneView.as_view())
