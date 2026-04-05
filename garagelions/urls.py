from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from account import views as account_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("home.urls")),
    path("account/", include("account.urls", namespace="account")),

    # shortcuts
    path("login/", account_views.user_login, name="login_shortcut"),
    path("logout/", account_views.user_logout, name="logout_shortcut"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)