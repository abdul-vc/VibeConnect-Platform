# Generated for Phase 11 – Showcase Domain Audit Actions

from django.conf import settings
from django.db import migrations, models


_ALL_ACTIONS = [
    'product_created', 'product_updated', 'product_retired',
    'organization_created', 'organization_updated', 'organization_retired',
    'entitlement_created', 'entitlement_status_changed', 'entitlement_revoked',
    'login_success', 'logout_success',
    'module_created', 'module_updated', 'module_retired',
    'feature_created', 'feature_updated', 'feature_retired',
    'capability_created', 'capability_updated', 'capability_retired',
    'plan_created', 'plan_updated',
    'plan_version_created', 'plan_version_updated', 'plan_version_cloned',
    'plan_version_activated', 'plan_version_retired',
    'plan_price_created', 'plan_price_updated', 'plan_price_removed',
    'plan_product_added', 'plan_product_removed',
    'plan_module_added', 'plan_module_removed',
    'plan_capability_added', 'plan_capability_removed',
    'plan_quota_created', 'plan_quota_updated', 'plan_quota_removed',
    'subscription_created', 'subscription_trial_started', 'subscription_trial_converted',
    'subscription_trial_expired', 'subscription_plan_changed', 'subscription_suspended',
    'subscription_reactivated', 'subscription_cancelled', 'subscription_reconciled',
    'user_created', 'user_updated', 'user_suspended', 'user_reactivated', 'user_disabled',
    'membership_created', 'membership_updated', 'membership_suspended',
    'membership_reactivated', 'membership_ended', 'membership_restored',
    'context_selected',
    'role_created', 'role_updated', 'role_permissions_changed', 'role_retired',
    'membership_role_assigned', 'console_module_policy_changed', 'permission_ceiling_changed',
    'user_product_assigned', 'user_product_suspended', 'user_product_reactivated',
    'user_product_revoked', 'user_module_assignments_replaced', 'seat_over_allocation_detected',
    'onboarding_step_transitioned',
    'invitation_issued', 'invitation_accepted', 'invitation_revoked',
    'bulk_import_job_created', 'bulk_import_job_committed',
    'access_request_created', 'access_request_approved', 'access_request_denied',
    'access_request_cancelled',
    # Phase 11 Showcase
    'showcase_profile_published', 'showcase_profile_unpublished', 'showcase_config_changed',
]

_ALL_ACTIONS_CHOICES = [(v, v.replace('_', ' ').title()) for v in _ALL_ACTIONS]

_ALL_TARGET_TYPES = [
    'product', 'organization', 'entitlement', 'auth',
    'module', 'feature', 'capability',
    'plan', 'plan_version', 'plan_price', 'plan_product', 'plan_module',
    'plan_capability', 'plan_quota',
    'subscription', 'user', 'membership',
    'role', 'console_policy', 'permission_ceiling',
    'user_product_assignment',
    'onboarding_case', 'invitation', 'bulk_import_job', 'access_request',
    # Phase 11
    'showcase_profile',
]

_ALL_TARGET_TYPES_CHOICES = [(v, v.replace('_', ' ').title()) for v in _ALL_TARGET_TYPES]


class Migration(migrations.Migration):

    dependencies = [
        ('auditlog', '0010_remove_auditlog_audit_action_valid_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Drop existing constraints
        migrations.RemoveConstraint(
            model_name='auditlog',
            name='audit_action_valid',
        ),
        migrations.RemoveConstraint(
            model_name='auditlog',
            name='audit_target_type_valid',
        ),
        # 2. Update field choices to include showcase values
        migrations.AlterField(
            model_name='auditlog',
            name='action',
            field=models.CharField(
                choices=_ALL_ACTIONS_CHOICES,
                editable=False,
                max_length=64,
            ),
        ),
        migrations.AlterField(
            model_name='auditlog',
            name='target_type',
            field=models.CharField(
                choices=_ALL_TARGET_TYPES_CHOICES,
                editable=False,
                max_length=64,
            ),
        ),
        # 3. Re-add constraints with new values
        migrations.AddConstraint(
            model_name='auditlog',
            constraint=models.CheckConstraint(
                condition=models.Q(action__in=_ALL_ACTIONS),
                name='audit_action_valid',
            ),
        ),
        migrations.AddConstraint(
            model_name='auditlog',
            constraint=models.CheckConstraint(
                condition=models.Q(target_type__in=_ALL_TARGET_TYPES),
                name='audit_target_type_valid',
            ),
        ),
    ]
