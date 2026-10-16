"""SSO Routing Configuration (Phase 5C)."""

from django.urls import path

from apps.integration_hub.sso_views import (
    SsoLaunchView,
    SsoPilotStatusView,
    SsoValidateView,
)

urlpatterns = [
    path("launch/", SsoLaunchView.as_view(), name="sso-launch"),
    path("validate/", SsoValidateView.as_view(), name="sso-validate"),
    path("pilot-status/", SsoPilotStatusView.as_view(), name="sso-pilot-status"),
]
