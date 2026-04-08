# account/urls.py

from django.urls import path
from . import views

app_name = 'account'

urlpatterns = [
    path('login/',                  views.user_login,               name='login'),
    path('logout/',                 views.user_logout,              name='logout'),
    path('profile/',                views.profile_edit,             name='profile_edit'),
    path('password-change/',        views.password_change_view,     name='password_change'),
    path('password-change/done/',   views.password_change_done_view,name='password_change_done'),
]