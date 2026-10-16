"""Entitlements Pagination.

Implements bounded page-number pagination with explicit validation for page_size.
"""

from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination


class EntitlementPagination(PageNumberPagination):
    """Standardized page-number pagination for entitlements catalog."""

    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_page_size(self, request):
        if self.page_size_query_param:
            raw_val = request.query_params.get(self.page_size_query_param)
            if raw_val is not None:
                try:
                    val = int(raw_val)
                    if val <= 0:
                        raise ValidationError({"page_size": ["page_size must be a positive integer."]})
                    return min(val, self.max_page_size)
                except (ValueError, TypeError):
                    raise ValidationError({"page_size": ["page_size must be a valid integer."]})
        return self.page_size
