"""Product Registry and Catalog Services.

Provides transactionally isolated, deadlock-free mutation services for Products,
ProductModules, ProductFeatures, and ProductCapabilities. Enforces strict top-down
locking (Product -> Module -> Feature -> Capability), non-authoritative preliminary
ancestry resolution with post-lock revalidation, all-ancestor activation gating,
bottom-up retirement, status-only retirement semantics, and trusted operation context.
"""

from typing import Any
import uuid

from django.db import transaction
from django.db.models import F
from rest_framework import exceptions

from apps.auditlog.models import AuditAction, AuditOperationSource, AuditTargetType
from apps.auditlog.services import AuditEventError, record_audit_event
from apps.product_registry.models import (
    ALLOWED_CATALOG_STATUS_TRANSITIONS,
    ALLOWED_STATUS_TRANSITIONS,
    CatalogStatus,
    Product,
    ProductCapability,
    ProductFeature,
    ProductModule,
    ProductStatus,
)


def _validate_trusted_context(
    operation_source: str,
    correlation_id: uuid.UUID | str | None,
) -> uuid.UUID | None:
    """Validates trusted operation source and correlation ID."""
    allowed_sources = (
        AuditOperationSource.INTERACTIVE,
        AuditOperationSource.BULK_IMPORT,
        AuditOperationSource.INTEGRATION,
    )
    if operation_source not in allowed_sources:
        raise ValueError(f"Operation source '{operation_source}' is not permitted for catalog mutations.")

    if operation_source in (AuditOperationSource.BULK_IMPORT, AuditOperationSource.INTEGRATION):
        if correlation_id is None:
            raise ValueError(f"Operation source '{operation_source}' requires a valid non-null correlation_id.")
        if isinstance(correlation_id, uuid.UUID):
            return correlation_id
        try:
            return uuid.UUID(str(correlation_id))
        except (ValueError, TypeError, AttributeError):
            raise ValueError(f"Invalid correlation_id '{correlation_id}'. Must be a valid UUID.")

    if correlation_id is not None:
        if isinstance(correlation_id, uuid.UUID):
            return correlation_id
        try:
            return uuid.UUID(str(correlation_id))
        except (ValueError, TypeError, AttributeError):
            raise ValueError(f"Invalid correlation_id '{correlation_id}'. Must be a valid UUID.")
    return None


def update_product(
    *,
    product_id: uuid.UUID | str,
    data: dict[str, Any],
    actor: Any,
) -> Product:
    """Updates a Product with race-safe locking, child module retirement checks, and audit logging."""
    with transaction.atomic():
        try:
            product = Product.objects.select_for_update().get(pk=product_id)
        except (Product.DoesNotExist, ValueError):
            raise exceptions.NotFound()

        from apps.product_registry.serializers import ProductUpdateSerializer

        prev_status = product.status
        prev_name = product.name
        prev_description = product.description

        serializer = ProductUpdateSerializer(instance=product, data=data, partial=True)
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data.get("status")
        new_name = serializer.validated_data.get("name")
        new_description = serializer.validated_data.get("description")

        # Phase 1E/1F Contract Preservation:
        if prev_status == ProductStatus.RETIRED:
            if new_status and new_status != ProductStatus.RETIRED:
                raise exceptions.ValidationError(
                    {"status": ["Cannot transition product out of retired."]}
                )

        # Validate lifecycle transition against locked status
        if new_status and new_status != product.status:
            allowed = ALLOWED_STATUS_TRANSITIONS.get(product.status, set())
            if new_status not in allowed:
                raise exceptions.ValidationError(
                    {"status": [f"Cannot transition product from '{product.status}' to '{new_status}'."]}
                )

            # When transitioning into RETIRED, check child modules
            if new_status == ProductStatus.RETIRED:
                if product.modules.exclude(status=CatalogStatus.RETIRED).exists():
                    raise exceptions.ValidationError(
                        {"status": ["Cannot retire product while it has non-retired modules."]}
                    )

        status_changed = bool(new_status and new_status != product.status)
        name_changed = bool(new_name is not None and new_name != product.name)
        desc_changed = bool(new_description is not None and new_description != product.description)

        # No-Op guard
        if not (status_changed or name_changed or desc_changed):
            return product

        product = serializer.save(updated_by=actor)
        resulting_status = product.status

        if status_changed and resulting_status == ProductStatus.RETIRED:
            action = AuditAction.PRODUCT_RETIRED
            metadata = {
                "name_changed": name_changed,
                "description_changed": desc_changed,
                "previous_status": prev_status,
                "resulting_status": resulting_status,
            }
        else:
            action = AuditAction.PRODUCT_UPDATED
            metadata = {
                "name_changed": name_changed,
                "description_changed": desc_changed,
                "status_changed": status_changed,
                "previous_status": prev_status,
                "resulting_status": resulting_status,
            }

        try:
            record_audit_event(
                action=action,
                target_type=AuditTargetType.PRODUCT,
                target_id=product.id,
                target_repr=product.name,
                actor=actor,
                organization_id=None,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata=metadata,
            )
        except AuditEventError as exc:
            raise exceptions.APIException("A server error occurred while recording the audit event.") from exc

        return product


# ==============================================================================
# PRODUCT MODULE SERVICES
# ==============================================================================

def create_product_module(
    *,
    product_id: uuid.UUID | str,
    data: dict[str, Any],
    actor: Any,
    operation_source: str = AuditOperationSource.INTERACTIVE,
    correlation_id: uuid.UUID | str | None = None,
) -> ProductModule:
    """Creates a new ProductModule under a locked non-retired Product."""
    corr_uuid = _validate_trusted_context(operation_source, correlation_id)

    with transaction.atomic():
        try:
            product = Product.objects.select_for_update().get(pk=product_id)
        except (Product.DoesNotExist, ValueError):
            raise exceptions.NotFound("Product not found.")

        if product.status == ProductStatus.RETIRED:
            raise exceptions.ValidationError({"product_id": ["Cannot create module under a retired product."]})

        serializer_data = {k: v for k, v in data.items() if k != "product_id"}
        serializer_data["product_id"] = str(product_id)

        from apps.product_registry.serializers import ProductModuleCreateSerializer
        serializer = ProductModuleCreateSerializer(data=serializer_data)
        serializer.is_valid(raise_exception=True)

        module = serializer.save(
            product=product,
            status=CatalogStatus.DRAFT,
            created_by=actor,
            updated_by=actor,
        )

        metadata = {
            "product_id": str(product.id),
            "product_code": product.code,
            "code": module.code,
            "name": module.name,
            "display_order": module.display_order,
            "status": module.status,
        }

        try:
            record_audit_event(
                action=AuditAction.MODULE_CREATED,
                target_type=AuditTargetType.MODULE,
                target_id=module.id,
                target_repr=module.name,
                actor=actor,
                organization_id=None,
                operation_source=operation_source,
                correlation_id=corr_uuid,
                metadata=metadata,
            )
        except AuditEventError as exc:
            raise exceptions.APIException("A server error occurred while recording the audit event.") from exc

        return module


def update_product_module(
    *,
    module_id: uuid.UUID | str,
    data: dict[str, Any],
    actor: Any,
    operation_source: str = AuditOperationSource.INTERACTIVE,
    correlation_id: uuid.UUID | str | None = None,
) -> ProductModule:
    """Updates or retires a ProductModule using top-down locking (Product -> Module)."""
    corr_uuid = _validate_trusted_context(operation_source, correlation_id)

    with transaction.atomic():
        # Preliminary read to find parent Product ID
        try:
            candidate_product_id = ProductModule.objects.values_list("product_id", flat=True).get(pk=module_id)
        except (ProductModule.DoesNotExist, ValueError):
            raise exceptions.NotFound("Module not found.")

        # Top-down lock acquisition
        product = Product.objects.select_for_update().get(pk=candidate_product_id)
        module = ProductModule.objects.select_for_update().get(pk=module_id)

        # Revalidate relationship
        if module.product_id != product.id:
            raise exceptions.ValidationError("Module parent relationship mismatch.")

        prev_status = module.status
        prev_name = module.name
        prev_code = module.code
        prev_description = module.description
        prev_order = module.display_order

        if prev_status == CatalogStatus.RETIRED:
            # Check if this is a no-op patch repeating retired
            new_status_requested = data.get("status")
            if new_status_requested == CatalogStatus.RETIRED and len(data) == 1:
                return module
            raise exceptions.ValidationError({"detail": "Cannot modify a retired catalog record."})

        from apps.product_registry.serializers import ProductModuleUpdateSerializer
        serializer = ProductModuleUpdateSerializer(instance=module, data=data, partial=True)
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data.get("status")
        new_name = serializer.validated_data.get("name")
        new_code = serializer.validated_data.get("code")
        new_description = serializer.validated_data.get("description")
        new_order = serializer.validated_data.get("display_order")

        # Retirement payload semantics: status-only
        if new_status == CatalogStatus.RETIRED:
            simultaneous_keys = set(data.keys()) - {"status"}
            if simultaneous_keys:
                raise exceptions.ValidationError(
                    {"detail": "Retirement is a status-only operation. Simultaneous field updates are not permitted."}
                )
            # Bottom-up check
            if module.features.exclude(status=CatalogStatus.RETIRED).exists():
                raise exceptions.ValidationError(
                    {"status": ["Cannot retire module while it has non-retired features."]}
                )

        # Code freeze check
        if new_code is not None and new_code != prev_code:
            if prev_status != CatalogStatus.DRAFT:
                raise exceptions.ValidationError({"code": ["Code cannot be modified after activation."]})

        # Status transition check
        if new_status and new_status != prev_status:
            allowed = ALLOWED_CATALOG_STATUS_TRANSITIONS.get(prev_status, set())
            if new_status not in allowed:
                raise exceptions.ValidationError(
                    {"status": [f"Cannot transition module from '{prev_status}' to '{new_status}'."]}
                )
            # All-ancestor activation gating
            if new_status == CatalogStatus.ACTIVE:
                if product.status != ProductStatus.ACTIVE:
                    raise exceptions.ValidationError(
                        {"status": ["Cannot activate module because parent product is not active."]}
                    )

        code_changed = bool(new_code is not None and new_code != prev_code)
        name_changed = bool(new_name is not None and new_name != prev_name)
        desc_changed = bool(new_description is not None and new_description != prev_description)
        order_changed = bool(new_order is not None and new_order != prev_order)
        status_changed = bool(new_status and new_status != prev_status)

        if not (code_changed or name_changed or desc_changed or order_changed or status_changed):
            return module

        module = serializer.save(updated_by=actor)
        resulting_status = module.status

        if status_changed and resulting_status == CatalogStatus.RETIRED:
            action = AuditAction.MODULE_RETIRED
            metadata = {
                "product_id": str(product.id),
                "product_code": product.code,
                "previous_status": prev_status,
                "resulting_status": resulting_status,
            }
        else:
            action = AuditAction.MODULE_UPDATED
            metadata = {
                "product_id": str(product.id),
                "product_code": product.code,
                "code_changed": code_changed,
                "name_changed": name_changed,
                "description_changed": desc_changed,
                "display_order_changed": order_changed,
                "status_changed": status_changed,
                "previous_status": prev_status,
                "resulting_status": resulting_status,
            }

        try:
            record_audit_event(
                action=action,
                target_type=AuditTargetType.MODULE,
                target_id=module.id,
                target_repr=module.name,
                actor=actor,
                organization_id=None,
                operation_source=operation_source,
                correlation_id=corr_uuid,
                metadata=metadata,
            )
        except AuditEventError as exc:
            raise exceptions.APIException("A server error occurred while recording the audit event.") from exc

        return module


def retire_product_module(
    *,
    module_id: uuid.UUID | str,
    actor: Any,
    operation_source: str = AuditOperationSource.INTERACTIVE,
    correlation_id: uuid.UUID | str | None = None,
) -> ProductModule:
    """Dedicated status-only retirement service for a ProductModule."""
    return update_product_module(
        module_id=module_id,
        data={"status": CatalogStatus.RETIRED},
        actor=actor,
        operation_source=operation_source,
        correlation_id=correlation_id,
    )


# ==============================================================================
# PRODUCT FEATURE SERVICES
# ==============================================================================

def create_product_feature(
    *,
    module_id: uuid.UUID | str,
    data: dict[str, Any],
    actor: Any,
    operation_source: str = AuditOperationSource.INTERACTIVE,
    correlation_id: uuid.UUID | str | None = None,
) -> ProductFeature:
    """Creates a new ProductFeature under a locked non-retired Module."""
    corr_uuid = _validate_trusted_context(operation_source, correlation_id)

    with transaction.atomic():
        # Preliminary read to find candidate Product ID from Module
        try:
            candidate_product_id = ProductModule.objects.values_list("product_id", flat=True).get(pk=module_id)
        except (ProductModule.DoesNotExist, ValueError):
            raise exceptions.NotFound("Module not found.")

        # Top-down lock acquisition
        product = Product.objects.select_for_update().get(pk=candidate_product_id)
        module = ProductModule.objects.select_for_update().get(pk=module_id)

        # Revalidate relationship
        if module.product_id != product.id:
            raise exceptions.ValidationError("Module parent relationship mismatch.")

        if module.status == CatalogStatus.RETIRED:
            raise exceptions.ValidationError({"module_id": ["Cannot create feature under a retired module."]})

        serializer_data = {k: v for k, v in data.items() if k != "module_id"}
        serializer_data["module_id"] = str(module_id)

        from apps.product_registry.serializers import ProductFeatureCreateSerializer
        serializer = ProductFeatureCreateSerializer(data=serializer_data)
        serializer.is_valid(raise_exception=True)

        feature = serializer.save(
            module=module,
            status=CatalogStatus.DRAFT,
            created_by=actor,
            updated_by=actor,
        )

        metadata = {
            "product_id": str(product.id),
            "product_code": product.code,
            "module_id": str(module.id),
            "module_code": module.code,
            "code": feature.code,
            "name": feature.name,
            "display_order": feature.display_order,
            "status": feature.status,
        }

        try:
            record_audit_event(
                action=AuditAction.FEATURE_CREATED,
                target_type=AuditTargetType.FEATURE,
                target_id=feature.id,
                target_repr=feature.name,
                actor=actor,
                organization_id=None,
                operation_source=operation_source,
                correlation_id=corr_uuid,
                metadata=metadata,
            )
        except AuditEventError as exc:
            raise exceptions.APIException("A server error occurred while recording the audit event.") from exc

        return feature


def update_product_feature(
    *,
    feature_id: uuid.UUID | str,
    data: dict[str, Any],
    actor: Any,
    operation_source: str = AuditOperationSource.INTERACTIVE,
    correlation_id: uuid.UUID | str | None = None,
) -> ProductFeature:
    """Updates or retires a ProductFeature using top-down locking (Product -> Module -> Feature)."""
    corr_uuid = _validate_trusted_context(operation_source, correlation_id)

    with transaction.atomic():
        # Preliminary reads to resolve ancestor chain
        try:
            candidate_module_id = ProductFeature.objects.values_list("module_id", flat=True).get(pk=feature_id)
            candidate_product_id = ProductModule.objects.values_list("product_id", flat=True).get(pk=candidate_module_id)
        except (ProductFeature.DoesNotExist, ProductModule.DoesNotExist, ValueError):
            raise exceptions.NotFound("Feature not found.")

        # Top-down lock acquisition
        product = Product.objects.select_for_update().get(pk=candidate_product_id)
        module = ProductModule.objects.select_for_update().get(pk=candidate_module_id)
        feature = ProductFeature.objects.select_for_update().get(pk=feature_id)

        # Revalidate ancestry chain
        if feature.module_id != module.id or module.product_id != product.id:
            raise exceptions.ValidationError("Feature ancestry chain mismatch.")

        prev_status = feature.status
        prev_name = feature.name
        prev_code = feature.code
        prev_description = feature.description
        prev_order = feature.display_order

        if prev_status == CatalogStatus.RETIRED:
            # Check if this is a no-op patch repeating retired
            new_status_requested = data.get("status")
            if new_status_requested == CatalogStatus.RETIRED and len(data) == 1:
                return feature
            raise exceptions.ValidationError({"detail": "Cannot modify a retired catalog record."})

        from apps.product_registry.serializers import ProductFeatureUpdateSerializer
        serializer = ProductFeatureUpdateSerializer(instance=feature, data=data, partial=True)
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data.get("status")
        new_name = serializer.validated_data.get("name")
        new_code = serializer.validated_data.get("code")
        new_description = serializer.validated_data.get("description")
        new_order = serializer.validated_data.get("display_order")

        # Retirement payload semantics: status-only
        if new_status == CatalogStatus.RETIRED:
            simultaneous_keys = set(data.keys()) - {"status"}
            if simultaneous_keys:
                raise exceptions.ValidationError(
                    {"detail": "Retirement is a status-only operation. Simultaneous field updates are not permitted."}
                )
            # Bottom-up check
            if feature.capabilities.exclude(status=CatalogStatus.RETIRED).exists():
                raise exceptions.ValidationError(
                    {"status": ["Cannot retire feature while it has non-retired capabilities."]}
                )

        # Code freeze check
        if new_code is not None and new_code != prev_code:
            if prev_status != CatalogStatus.DRAFT:
                raise exceptions.ValidationError({"code": ["Code cannot be modified after activation."]})

        # Status transition check
        if new_status and new_status != prev_status:
            allowed = ALLOWED_CATALOG_STATUS_TRANSITIONS.get(prev_status, set())
            if new_status not in allowed:
                raise exceptions.ValidationError(
                    {"status": [f"Cannot transition feature from '{prev_status}' to '{new_status}'."]}
                )
            # All-ancestor activation gating
            if new_status == CatalogStatus.ACTIVE:
                if product.status != ProductStatus.ACTIVE or module.status != CatalogStatus.ACTIVE:
                    raise exceptions.ValidationError(
                        {"status": ["Cannot activate feature because an ancestor is not active."]}
                    )

        code_changed = bool(new_code is not None and new_code != prev_code)
        name_changed = bool(new_name is not None and new_name != prev_name)
        desc_changed = bool(new_description is not None and new_description != prev_description)
        order_changed = bool(new_order is not None and new_order != prev_order)
        status_changed = bool(new_status and new_status != prev_status)

        if not (code_changed or name_changed or desc_changed or order_changed or status_changed):
            return feature

        feature = serializer.save(updated_by=actor)
        resulting_status = feature.status

        if status_changed and resulting_status == CatalogStatus.RETIRED:
            action = AuditAction.FEATURE_RETIRED
            metadata = {
                "product_id": str(product.id),
                "product_code": product.code,
                "module_id": str(module.id),
                "module_code": module.code,
                "previous_status": prev_status,
                "resulting_status": resulting_status,
            }
        else:
            action = AuditAction.FEATURE_UPDATED
            metadata = {
                "product_id": str(product.id),
                "product_code": product.code,
                "module_id": str(module.id),
                "module_code": module.code,
                "code_changed": code_changed,
                "name_changed": name_changed,
                "description_changed": desc_changed,
                "display_order_changed": order_changed,
                "status_changed": status_changed,
                "previous_status": prev_status,
                "resulting_status": resulting_status,
            }

        try:
            record_audit_event(
                action=action,
                target_type=AuditTargetType.FEATURE,
                target_id=feature.id,
                target_repr=feature.name,
                actor=actor,
                organization_id=None,
                operation_source=operation_source,
                correlation_id=corr_uuid,
                metadata=metadata,
            )
        except AuditEventError as exc:
            raise exceptions.APIException("A server error occurred while recording the audit event.") from exc

        return feature


def retire_product_feature(
    *,
    feature_id: uuid.UUID | str,
    actor: Any,
    operation_source: str = AuditOperationSource.INTERACTIVE,
    correlation_id: uuid.UUID | str | None = None,
) -> ProductFeature:
    """Dedicated status-only retirement service for a ProductFeature."""
    return update_product_feature(
        feature_id=feature_id,
        data={"status": CatalogStatus.RETIRED},
        actor=actor,
        operation_source=operation_source,
        correlation_id=correlation_id,
    )


# ==============================================================================
# PRODUCT CAPABILITY SERVICES
# ==============================================================================

def create_product_capability(
    *,
    feature_id: uuid.UUID | str,
    data: dict[str, Any],
    actor: Any,
    operation_source: str = AuditOperationSource.INTERACTIVE,
    correlation_id: uuid.UUID | str | None = None,
) -> ProductCapability:
    """Creates a new ProductCapability under a locked non-retired Feature."""
    corr_uuid = _validate_trusted_context(operation_source, correlation_id)

    with transaction.atomic():
        # Preliminary reads to resolve candidate ancestors
        try:
            candidate_module_id = ProductFeature.objects.values_list("module_id", flat=True).get(pk=feature_id)
            candidate_product_id = ProductModule.objects.values_list("product_id", flat=True).get(pk=candidate_module_id)
        except (ProductFeature.DoesNotExist, ProductModule.DoesNotExist, ValueError):
            raise exceptions.NotFound("Feature not found.")

        # Top-down lock acquisition
        product = Product.objects.select_for_update().get(pk=candidate_product_id)
        module = ProductModule.objects.select_for_update().get(pk=candidate_module_id)
        feature = ProductFeature.objects.select_for_update().get(pk=feature_id)

        # Revalidate ancestry chain
        if feature.module_id != module.id or module.product_id != product.id:
            raise exceptions.ValidationError("Capability ancestry chain mismatch.")

        if feature.status == CatalogStatus.RETIRED:
            raise exceptions.ValidationError({"feature_id": ["Cannot create capability under a retired feature."]})

        serializer_data = {k: v for k, v in data.items() if k != "feature_id"}
        serializer_data["feature_id"] = str(feature_id)

        from apps.product_registry.serializers import ProductCapabilityCreateSerializer
        serializer = ProductCapabilityCreateSerializer(data=serializer_data)
        serializer.is_valid(raise_exception=True)

        capability = serializer.save(
            feature=feature,
            status=CatalogStatus.DRAFT,
            created_by=actor,
            updated_by=actor,
        )

        metadata = {
            "product_id": str(product.id),
            "product_code": product.code,
            "module_id": str(module.id),
            "module_code": module.code,
            "feature_id": str(feature.id),
            "feature_code": feature.code,
            "code": capability.code,
            "name": capability.name,
            "display_order": capability.display_order,
            "status": capability.status,
        }

        try:
            record_audit_event(
                action=AuditAction.CAPABILITY_CREATED,
                target_type=AuditTargetType.CAPABILITY,
                target_id=capability.id,
                target_repr=capability.name,
                actor=actor,
                organization_id=None,
                operation_source=operation_source,
                correlation_id=corr_uuid,
                metadata=metadata,
            )
        except AuditEventError as exc:
            raise exceptions.APIException("A server error occurred while recording the audit event.") from exc

        return capability


def update_product_capability(
    *,
    capability_id: uuid.UUID | str,
    data: dict[str, Any],
    actor: Any,
    operation_source: str = AuditOperationSource.INTERACTIVE,
    correlation_id: uuid.UUID | str | None = None,
) -> ProductCapability:
    """Updates or retires a ProductCapability using top-down locking."""
    corr_uuid = _validate_trusted_context(operation_source, correlation_id)

    with transaction.atomic():
        # Preliminary reads to resolve complete ancestor chain
        try:
            candidate_feature_id = ProductCapability.objects.values_list("feature_id", flat=True).get(pk=capability_id)
            candidate_module_id = ProductFeature.objects.values_list("module_id", flat=True).get(pk=candidate_feature_id)
            candidate_product_id = ProductModule.objects.values_list("product_id", flat=True).get(pk=candidate_module_id)
        except (ProductCapability.DoesNotExist, ProductFeature.DoesNotExist, ProductModule.DoesNotExist, ValueError):
            raise exceptions.NotFound("Capability not found.")

        # Top-down lock acquisition
        product = Product.objects.select_for_update().get(pk=candidate_product_id)
        module = ProductModule.objects.select_for_update().get(pk=candidate_module_id)
        feature = ProductFeature.objects.select_for_update().get(pk=candidate_feature_id)
        capability = ProductCapability.objects.select_for_update().get(pk=capability_id)

        # Revalidate ancestry chain
        if (
            capability.feature_id != feature.id
            or feature.module_id != module.id
            or module.product_id != product.id
        ):
            raise exceptions.ValidationError("Capability ancestry chain mismatch.")

        prev_status = capability.status
        prev_name = capability.name
        prev_code = capability.code
        prev_description = capability.description
        prev_order = capability.display_order

        if prev_status == CatalogStatus.RETIRED:
            # Check if this is a no-op patch repeating retired
            new_status_requested = data.get("status")
            if new_status_requested == CatalogStatus.RETIRED and len(data) == 1:
                return capability
            raise exceptions.ValidationError({"detail": "Cannot modify a retired catalog record."})

        from apps.product_registry.serializers import ProductCapabilityUpdateSerializer
        serializer = ProductCapabilityUpdateSerializer(instance=capability, data=data, partial=True)
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data.get("status")
        new_name = serializer.validated_data.get("name")
        new_code = serializer.validated_data.get("code")
        new_description = serializer.validated_data.get("description")
        new_order = serializer.validated_data.get("display_order")

        # Retirement payload semantics: status-only
        if new_status == CatalogStatus.RETIRED:
            simultaneous_keys = set(data.keys()) - {"status"}
            if simultaneous_keys:
                raise exceptions.ValidationError(
                    {"detail": "Retirement is a status-only operation. Simultaneous field updates are not permitted."}
                )

        # Code freeze check
        if new_code is not None and new_code != prev_code:
            if prev_status != CatalogStatus.DRAFT:
                raise exceptions.ValidationError({"code": ["Code cannot be modified after activation."]})

        # Status transition check
        if new_status and new_status != prev_status:
            allowed = ALLOWED_CATALOG_STATUS_TRANSITIONS.get(prev_status, set())
            if new_status not in allowed:
                raise exceptions.ValidationError(
                    {"status": [f"Cannot transition capability from '{prev_status}' to '{new_status}'."]}
                )
            # All-ancestor activation gating
            if new_status == CatalogStatus.ACTIVE:
                if (
                    product.status != ProductStatus.ACTIVE
                    or module.status != CatalogStatus.ACTIVE
                    or feature.status != CatalogStatus.ACTIVE
                ):
                    raise exceptions.ValidationError(
                        {"status": ["Cannot activate capability because an ancestor is not active."]}
                    )

        code_changed = bool(new_code is not None and new_code != prev_code)
        name_changed = bool(new_name is not None and new_name != prev_name)
        desc_changed = bool(new_description is not None and new_description != prev_description)
        order_changed = bool(new_order is not None and new_order != prev_order)
        status_changed = bool(new_status and new_status != prev_status)

        if not (code_changed or name_changed or desc_changed or order_changed or status_changed):
            return capability

        capability = serializer.save(updated_by=actor)
        resulting_status = capability.status

        if status_changed and resulting_status == CatalogStatus.RETIRED:
            action = AuditAction.CAPABILITY_RETIRED
            metadata = {
                "product_id": str(product.id),
                "product_code": product.code,
                "module_id": str(module.id),
                "module_code": module.code,
                "feature_id": str(feature.id),
                "feature_code": feature.code,
                "previous_status": prev_status,
                "resulting_status": resulting_status,
            }
        else:
            action = AuditAction.CAPABILITY_UPDATED
            metadata = {
                "product_id": str(product.id),
                "product_code": product.code,
                "module_id": str(module.id),
                "module_code": module.code,
                "feature_id": str(feature.id),
                "feature_code": feature.code,
                "code_changed": code_changed,
                "name_changed": name_changed,
                "description_changed": desc_changed,
                "display_order_changed": order_changed,
                "status_changed": status_changed,
                "previous_status": prev_status,
                "resulting_status": resulting_status,
            }

        try:
            record_audit_event(
                action=action,
                target_type=AuditTargetType.CAPABILITY,
                target_id=capability.id,
                target_repr=capability.name,
                actor=actor,
                organization_id=None,
                operation_source=operation_source,
                correlation_id=corr_uuid,
                metadata=metadata,
            )
        except AuditEventError as exc:
            raise exceptions.APIException("A server error occurred while recording the audit event.") from exc

        return capability


def retire_product_capability(
    *,
    capability_id: uuid.UUID | str,
    actor: Any,
    operation_source: str = AuditOperationSource.INTERACTIVE,
    correlation_id: uuid.UUID | str | None = None,
) -> ProductCapability:
    """Dedicated status-only retirement service for a ProductCapability."""
    return update_product_capability(
        capability_id=capability_id,
        data={"status": CatalogStatus.RETIRED},
        actor=actor,
        operation_source=operation_source,
        correlation_id=correlation_id,
    )
