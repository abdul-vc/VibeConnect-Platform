# Generated manually for VibeConnect Phase 2E Stage 1

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("auditlog", "0005_phase2d_audit_actions"),
        ("organizations", "0003_organizationmembership_role"),
    ]

    operations = [
        # --- Remove constraints referencing expanded value lists ---
        migrations.RemoveConstraint(
            model_name="auditlog",
            name="audit_action_valid",
        ),
        migrations.RemoveConstraint(
            model_name="auditlog",
            name="audit_target_type_valid",
        ),
        migrations.RemoveConstraint(
            model_name="auditlog",
            name="audit_membership_target_match",
        ),
        # --- Update field choices to reflect expanded enums ---
        migrations.AlterField(
            model_name="auditlog",
            name="action",
            field=models.CharField(
                choices=[
                    ("product_created", "Product Created"),
                    ("product_updated", "Product Updated"),
                    ("product_retired", "Product Retired"),
                    ("organization_created", "Organization Created"),
                    ("organization_updated", "Organization Updated"),
                    ("organization_retired", "Organization Retired"),
                    ("entitlement_created", "Entitlement Created"),
                    ("entitlement_status_changed", "Entitlement Status Changed"),
                    ("entitlement_revoked", "Entitlement Revoked"),
                    ("login_success", "Login Success"),
                    ("logout_success", "Logout Success"),
                    ("module_created", "Module Created"),
                    ("module_updated", "Module Updated"),
                    ("module_retired", "Module Retired"),
                    ("feature_created", "Feature Created"),
                    ("feature_updated", "Feature Updated"),
                    ("feature_retired", "Feature Retired"),
                    ("capability_created", "Capability Created"),
                    ("capability_updated", "Capability Updated"),
                    ("capability_retired", "Capability Retired"),
                    ("plan_created", "Plan Created"),
                    ("plan_updated", "Plan Updated"),
                    ("plan_version_created", "Plan Version Created"),
                    ("plan_version_updated", "Plan Version Updated"),
                    ("plan_version_cloned", "Plan Version Cloned"),
                    ("plan_version_activated", "Plan Version Activated"),
                    ("plan_version_retired", "Plan Version Retired"),
                    ("plan_price_created", "Plan Price Created"),
                    ("plan_price_updated", "Plan Price Updated"),
                    ("plan_price_removed", "Plan Price Removed"),
                    ("plan_product_added", "Plan Product Added"),
                    ("plan_product_removed", "Plan Product Removed"),
                    ("plan_module_added", "Plan Module Added"),
                    ("plan_module_removed", "Plan Module Removed"),
                    ("plan_capability_added", "Plan Capability Added"),
                    ("plan_capability_removed", "Plan Capability Removed"),
                    ("plan_quota_created", "Plan Quota Created"),
                    ("plan_quota_updated", "Plan Quota Updated"),
                    ("plan_quota_removed", "Plan Quota Removed"),
                    # Phase 2C
                    ("subscription_created", "Subscription Created"),
                    ("subscription_trial_started", "Subscription Trial Started"),
                    ("subscription_trial_converted", "Subscription Trial Converted"),
                    ("subscription_trial_expired", "Subscription Trial Expired"),
                    ("subscription_plan_changed", "Subscription Plan Changed"),
                    ("subscription_suspended", "Subscription Suspended"),
                    ("subscription_reactivated", "Subscription Reactivated"),
                    ("subscription_cancelled", "Subscription Cancelled"),
                    ("subscription_reconciled", "Subscription Reconciled"),
                    # Phase 2D
                    ("user_created", "User Created"),
                    ("user_updated", "User Updated"),
                    ("user_suspended", "User Suspended"),
                    ("user_reactivated", "User Reactivated"),
                    ("user_disabled", "User Disabled"),
                    ("membership_created", "Membership Created"),
                    ("membership_updated", "Membership Updated"),
                    ("membership_suspended", "Membership Suspended"),
                    ("membership_reactivated", "Membership Reactivated"),
                    ("membership_ended", "Membership Ended"),
                    ("membership_restored", "Membership Restored"),
                    ("context_selected", "Context Selected"),
                    # Phase 2E
                    ("role_created", "Role Created"),
                    ("role_updated", "Role Updated"),
                    ("role_permissions_changed", "Role Permissions Changed"),
                    ("role_retired", "Role Retired"),
                    ("membership_role_assigned", "Membership Role Assigned"),
                    ("console_module_policy_changed", "Console Module Policy Changed"),
                    ("permission_ceiling_changed", "Permission Ceiling Changed"),
                ],
                editable=False,
                max_length=64,
            ),
        ),
        migrations.AlterField(
            model_name="auditlog",
            name="target_type",
            field=models.CharField(
                choices=[
                    ("product", "Product"),
                    ("organization", "Organization"),
                    ("entitlement", "Entitlement"),
                    ("auth", "Authentication"),
                    ("module", "Module"),
                    ("feature", "Feature"),
                    ("capability", "Capability"),
                    ("plan", "Plan"),
                    ("plan_version", "Plan Version"),
                    ("plan_price", "Plan Price"),
                    ("plan_product", "Plan Product"),
                    ("plan_module", "Plan Module"),
                    ("plan_capability", "Plan Capability"),
                    ("plan_quota", "Plan Quota"),
                    ("subscription", "Subscription"),
                    # Phase 2D
                    ("user", "User"),
                    ("membership", "Membership"),
                    # Phase 2E
                    ("role", "Role"),
                    ("console_policy", "Console Module Policy"),
                    ("permission_ceiling", "Permission Ceiling"),
                ],
                editable=False,
                max_length=64,
            ),
        ),
        # --- Re-add expanded audit_action_valid ---
        migrations.AddConstraint(
            model_name="auditlog",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("action__in", [
                        "product_created", "product_updated", "product_retired",
                        "organization_created", "organization_updated", "organization_retired",
                        "entitlement_created", "entitlement_status_changed", "entitlement_revoked",
                        "login_success", "logout_success",
                        "module_created", "module_updated", "module_retired",
                        "feature_created", "feature_updated", "feature_retired",
                        "capability_created", "capability_updated", "capability_retired",
                        "plan_created", "plan_updated",
                        "plan_version_created", "plan_version_updated", "plan_version_cloned",
                        "plan_version_activated", "plan_version_retired",
                        "plan_price_created", "plan_price_updated", "plan_price_removed",
                        "plan_product_added", "plan_product_removed",
                        "plan_module_added", "plan_module_removed",
                        "plan_capability_added", "plan_capability_removed",
                        "plan_quota_created", "plan_quota_updated", "plan_quota_removed",
                        "subscription_created", "subscription_trial_started",
                        "subscription_trial_converted", "subscription_trial_expired",
                        "subscription_plan_changed", "subscription_suspended",
                        "subscription_reactivated", "subscription_cancelled",
                        "subscription_reconciled",
                        # Phase 2D
                        "user_created", "user_updated", "user_suspended",
                        "user_reactivated", "user_disabled",
                        "membership_created", "membership_updated", "membership_suspended",
                        "membership_reactivated", "membership_ended", "membership_restored",
                        "context_selected",
                        # Phase 2E
                        "role_created", "role_updated", "role_permissions_changed",
                        "role_retired", "membership_role_assigned",
                        "console_module_policy_changed", "permission_ceiling_changed",
                    ])
                ),
                name="audit_action_valid",
            ),
        ),
        # --- Re-add expanded audit_target_type_valid ---
        migrations.AddConstraint(
            model_name="auditlog",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("target_type__in", [
                        "product", "organization", "entitlement", "auth",
                        "module", "feature", "capability",
                        "plan", "plan_version", "plan_price",
                        "plan_product", "plan_module", "plan_capability", "plan_quota",
                        "subscription",
                        # Phase 2D
                        "user", "membership",
                        # Phase 2E
                        "role", "console_policy", "permission_ceiling",
                    ])
                ),
                name="audit_target_type_valid",
            ),
        ),
        # --- Phase 2E: membership action -> target_type match (including membership_role_assigned) ---
        migrations.AddConstraint(
            model_name="auditlog",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("action__in", [
                            "membership_created", "membership_updated", "membership_suspended",
                            "membership_reactivated", "membership_ended", "membership_restored",
                            "membership_role_assigned",
                        ]),
                        _negated=True,
                    ),
                    ("target_type", "membership"),
                    _connector="OR",
                ),
                name="audit_membership_target_match",
            ),
        ),
        # --- Phase 2E: role action -> target_type match ---
        migrations.AddConstraint(
            model_name="auditlog",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("action__in", [
                            "role_created", "role_updated",
                            "role_permissions_changed", "role_retired",
                        ]),
                        _negated=True,
                    ),
                    ("target_type", "role"),
                    _connector="OR",
                ),
                name="audit_role_target_match",
            ),
        ),
        # --- Phase 2E: console_module_policy action -> target_type match ---
        migrations.AddConstraint(
            model_name="auditlog",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("action", "console_module_policy_changed"), _negated=True),
                    ("target_type", "console_policy"),
                    _connector="OR",
                ),
                name="audit_console_policy_target_match",
            ),
        ),
        # --- Phase 2E: permission_ceiling action -> target_type match ---
        migrations.AddConstraint(
            model_name="auditlog",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("action", "permission_ceiling_changed"), _negated=True),
                    ("target_type", "permission_ceiling"),
                    _connector="OR",
                ),
                name="audit_permission_ceiling_target_match",
            ),
        ),
        # --- Phase 2E: role audit events must carry organization_id ---
        migrations.AddConstraint(
            model_name="auditlog",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("target_type", "role"), _negated=True),
                    ("organization_id__isnull", False),
                    _connector="OR",
                ),
                name="audit_role_org_id_req",
            ),
        ),
        # --- Phase 2E: console_policy audit events must carry organization_id ---
        migrations.AddConstraint(
            model_name="auditlog",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("target_type", "console_policy"), _negated=True),
                    ("organization_id__isnull", False),
                    _connector="OR",
                ),
                name="audit_console_policy_org_id_req",
            ),
        ),
        # --- Phase 2E: permission_ceiling audit events must carry organization_id ---
        migrations.AddConstraint(
            model_name="auditlog",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("target_type", "permission_ceiling"), _negated=True),
                    ("organization_id__isnull", False),
                    _connector="OR",
                ),
                name="audit_permission_ceiling_org_id_req",
            ),
        ),
    ]
