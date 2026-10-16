"""REST API Views for Access Requests & Approvals (Phase 3F)."""

from django.db.models import Q
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access_requests.models import AccessRequest
from apps.access_requests.serializers import (
    AccessRequestSerializer,
    CreateAccessRequestSerializer,
    DecideAccessRequestSerializer,
)
from apps.access_requests.services import (
    AccessRequestError,
    AccessRequestNotFoundError,
    DuplicateAccessRequestError,
    InvalidReasonError,
    InvalidRequestStatusError,
    approve_access_request,
    cancel_access_request,
    create_access_request,
    deny_access_request,
)
from apps.assignments.services import (
    AlreadyAssignedError,
    AssignmentServiceError,
    MembershipIneligibleError,
    ProductInactiveError,
    SeatLimitExceededError,
)
from apps.access_control.services.evaluation import evaluate_access
from apps.organizations.models import MembershipStatus, MembershipType, OrganizationMembership


class StandardResultsPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


def _can_decide(user, organization) -> bool:
    if getattr(user, "is_platform_owner", False):
        return True
    if not organization:
        return False
    eval_result = evaluate_access(user, "tenant", organization.id)
    return eval_result.has_permission("access_requests.decide") or eval_result.has_permission("access_requests.manage")


def _can_view_org(user, organization_id) -> bool:
    if getattr(user, "is_platform_owner", False):
        return True
    eval_result = evaluate_access(user, "tenant", organization_id)
    return eval_result.has_permission("access_requests.view")


class AccessRequestListCreateView(APIView):
    """List and create product access requests."""

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsPagination

    def get(self, request):
        user = request.user
        is_owner = getattr(user, "is_platform_owner", False)

        active_org_ids = list(
            user.organization_memberships.filter(
                status=MembershipStatus.ACTIVE,
            ).values_list("organization_id", flat=True)
        )
        allowed_view_org_ids = [
            org_id for org_id in active_org_ids
            if _can_view_org(user, org_id)
        ]

        qs = (
            AccessRequest.objects.select_related("organization", "requester", "product")
            .prefetch_related("decisions__approver")
            .all()
        )

        # Scoping
        if is_owner:
            pass  # Owner sees all
        elif allowed_view_org_ids:
            # Tenant admin/reviewer sees all requests in their authorized orgs OR their own requests
            qs = qs.filter(Q(organization_id__in=allowed_view_org_ids) | Q(requester=user))
        else:
            # Regular user only sees their own requests
            qs = qs.filter(requester=user)

        # Filters
        org_filter = request.query_params.get("organization_id")
        if org_filter:
            qs = qs.filter(organization_id=org_filter)

        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        product_filter = request.query_params.get("product_id")
        if product_filter:
            qs = qs.filter(product_id=product_filter)

        search_query = request.query_params.get("search")
        if search_query:
            qs = qs.filter(
                Q(requester__email__icontains=search_query)
                | Q(requester__full_name__icontains=search_query)
                | Q(product__name__icontains=search_query)
                | Q(product__code__icontains=search_query)
            )

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)
        serializer = AccessRequestSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = CreateAccessRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        org = data["organization_id"]
        prod = data["product_id"]

        try:
            req = create_access_request(
                organization=org,
                requester=request.user,
                product=prod,
                requested_modules=data.get("requested_modules"),
                reason=data.get("reason", ""),
            )
            return Response(AccessRequestSerializer(req).data, status=status.HTTP_201_CREATED)
        except DuplicateAccessRequestError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_409_CONFLICT)
        except AlreadyAssignedError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_409_CONFLICT)
        except (MembershipIneligibleError, ProductInactiveError) as exc:
            return Response({"detail": str(exc), "code": getattr(exc, "code", "VALIDATION_ERROR")}, status=status.HTTP_400_BAD_REQUEST)
        except AccessRequestError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_400_BAD_REQUEST)


class AccessRequestDetailView(APIView):
    """Retrieve an access request with decision history."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk: str):
        try:
            req = (
                AccessRequest.objects.select_related("organization", "requester", "product")
                .prefetch_related("decisions__approver")
                .get(id=pk)
            )
        except AccessRequest.DoesNotExist:
            return Response({"detail": "Access request not found."}, status=status.HTTP_404_NOT_FOUND)

        is_owner = getattr(request.user, "is_platform_owner", False)
        is_requester = request.user.id == req.requester_id
        can_view = _can_view_org(request.user, req.organization_id)

        if not (is_owner or is_requester or can_view):
            raise PermissionDenied("You do not have permission to view this access request.")

        return Response(AccessRequestSerializer(req).data)


class AccessRequestApproveView(APIView):
    """Approve a pending access request."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk: str):
        try:
            req = AccessRequest.objects.select_related("organization").get(id=pk)
        except AccessRequest.DoesNotExist:
            return Response({"detail": "Access request not found."}, status=status.HTTP_404_NOT_FOUND)

        if not _can_decide(request.user, req.organization):
            raise PermissionDenied("You do not have permission to approve access requests for this organization.")

        serializer = DecideAccessRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get("reason", "")

        try:
            approved_req, assignment = approve_access_request(
                request_id=req.id,
                approver=request.user,
                reason=reason,
            )
            data = AccessRequestSerializer(approved_req).data
            data["assignment_id"] = str(assignment.id) if assignment else None
            return Response(data, status=status.HTTP_200_OK)
        except SeatLimitExceededError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_409_CONFLICT)
        except InvalidRequestStatusError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_409_CONFLICT)
        except MembershipIneligibleError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_400_BAD_REQUEST)
        except AssignmentServiceError as exc:
            return Response({"detail": str(exc), "code": getattr(exc, "code", "ASSIGNMENT_FAILED")}, status=status.HTTP_400_BAD_REQUEST)
        except AccessRequestError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_400_BAD_REQUEST)


class AccessRequestDenyView(APIView):
    """Deny a pending access request with mandatory reason."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk: str):
        try:
            req = AccessRequest.objects.select_related("organization").get(id=pk)
        except AccessRequest.DoesNotExist:
            return Response({"detail": "Access request not found."}, status=status.HTTP_404_NOT_FOUND)

        if not _can_decide(request.user, req.organization):
            raise PermissionDenied("You do not have permission to deny access requests for this organization.")

        serializer = DecideAccessRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get("reason", "")

        try:
            denied_req = deny_access_request(
                request_id=req.id,
                approver=request.user,
                reason=reason,
            )
            return Response(AccessRequestSerializer(denied_req).data, status=status.HTTP_200_OK)
        except InvalidReasonError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_400_BAD_REQUEST)
        except InvalidRequestStatusError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_409_CONFLICT)
        except AccessRequestError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_400_BAD_REQUEST)


class AccessRequestCancelView(APIView):
    """Cancel a pending access request."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk: str):
        try:
            req = AccessRequest.objects.select_related("organization").get(id=pk)
        except AccessRequest.DoesNotExist:
            return Response({"detail": "Access request not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            cancelled_req = cancel_access_request(
                request_id=req.id,
                actor=request.user,
            )
            return Response(AccessRequestSerializer(cancelled_req).data, status=status.HTTP_200_OK)
        except InvalidRequestStatusError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_409_CONFLICT)
        except AccessRequestError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_400_BAD_REQUEST)
