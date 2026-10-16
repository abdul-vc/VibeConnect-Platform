"""Identity URL Configuration.

Routes authentication endpoints under /api/v1/auth/.
"""

from django.urls import path
from .views import ContextSelectionView, CsrfTokenView, CurrentUserView, LoginView, LogoutView

urlpatterns = [
    path("csrf/", CsrfTokenView.as_view(), name="auth_csrf"),
    path("login/", LoginView.as_view(), name="auth_login"),
    path("me/", CurrentUserView.as_view(), name="auth_me"),
    path("logout/", LogoutView.as_view(), name="auth_logout"),
    path("context/", ContextSelectionView.as_view(), name="auth_context_selection"),
]
