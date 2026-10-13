"""Central User URL Routing.

Maps central user management endpoints:
- GET, POST /api/v1/users/
- GET, PATCH /api/v1/users/<uuid:pk>/
- POST /api/v1/users/<uuid:pk>/suspend/
- POST /api/v1/users/<uuid:pk>/reactivate/
- POST /api/v1/users/<uuid:pk>/disable/
"""

from django.urls import path
from apps.identity.user_views import UserViewSet

user_list = UserViewSet.as_view({
    "get": "list",
    "post": "create",
})

user_detail = UserViewSet.as_view({
    "get": "retrieve",
    "patch": "partial_update",
})

user_suspend = UserViewSet.as_view({"post": "suspend"})
user_reactivate = UserViewSet.as_view({"post": "reactivate"})
user_disable = UserViewSet.as_view({"post": "disable"})
user_anonymize = UserViewSet.as_view({"post": "anonymize"})

urlpatterns = [
    path("", user_list, name="user-list"),
    path("<uuid:pk>/", user_detail, name="user-detail"),
    path("<uuid:pk>/suspend/", user_suspend, name="user-suspend"),
    path("<uuid:pk>/reactivate/", user_reactivate, name="user-reactivate"),
    path("<uuid:pk>/disable/", user_disable, name="user-disable"),
    path("<uuid:pk>/anonymize/", user_anonymize, name="user-anonymize"),
]
