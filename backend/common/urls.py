"""Common URL configuration."""

from django.urls import path
from .views import HealthCheckView, ReadinessCheckView

urlpatterns = [
    path("health/ready/", ReadinessCheckView.as_view(), name="readiness_check"),
    path("health/", HealthCheckView.as_view(), name="health_check"),
]
