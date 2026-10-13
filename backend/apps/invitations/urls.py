"""URL routing for Invitations (Phase 3C)."""

from django.urls import path

from apps.invitations.views import (
    AcceptInvitationView,
    IssueInvitationView,
    ValidateInvitationView,
)

urlpatterns = [
    path("", IssueInvitationView.as_view(), name="invitation-issue"),
    path("<str:token>/", ValidateInvitationView.as_view(), name="invitation-validate"),
    path("<str:token>/accept/", AcceptInvitationView.as_view(), name="invitation-accept"),
]
