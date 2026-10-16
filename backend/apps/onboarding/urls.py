"""Onboarding URL Routing."""

from rest_framework.routers import SimpleRouter
from apps.onboarding.views import TenantOnboardingCaseViewSet

router = SimpleRouter()
router.register(r"cases", TenantOnboardingCaseViewSet, basename="onboarding-cases")

urlpatterns = router.urls
