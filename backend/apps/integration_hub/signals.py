"""Signal receivers for automatic integration lifecycle triggers."""

import logging
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.integration_hub.lifecycle_service import (
    handle_tenant_deactivated_or_suspended,
    handle_tenant_lms_entitlement_activated,
    is_lms_product,
)
from apps.subscriptions.models import SubscriptionProductEntitlement, SubscriptionStatus

logger = logging.getLogger(__name__)


@receiver(post_save, sender=OrganizationProductEntitlement)
def on_org_product_entitlement_saved(sender, instance, created, **kwargs):
    """Automatically synchronizes direct OrganizationProductEntitlement changes with LMS."""
    if not is_lms_product(instance.product):
        return

    if instance.status == EntitlementStatus.ACTIVE:
        handle_tenant_lms_entitlement_activated(
            instance.organization,
            source="entitlement_post_save",
        )
    elif instance.status in (EntitlementStatus.SUSPENDED, EntitlementStatus.REVOKED):
        handle_tenant_deactivated_or_suspended(
            instance.organization,
            status=instance.status,
            reason="Entitlement status updated",
        )


@receiver(post_save, sender=SubscriptionProductEntitlement)
def on_subscription_product_entitlement_saved(sender, instance, created, **kwargs):
    """Automatically synchronizes subscription-based LMS entitlements."""
    if not is_lms_product(instance.product):
        return

    if instance.subscription and instance.subscription.status == SubscriptionStatus.ACTIVE:
        handle_tenant_lms_entitlement_activated(
            instance.organization,
            source="subscription_entitlement_post_save",
        )
