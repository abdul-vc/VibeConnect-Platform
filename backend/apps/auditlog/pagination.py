"""Audit Log Pagination.

Implements bounded page-number pagination with explicit validation for page_size.
"""

from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination


class AuditLogPagination(PageNumberPagination):
    """Standardized page-number pagination for audit log entries."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_page_size(self, request):
        if self.page_size_query_param:
            raw_val = request.query_params.get(self.page_size_query_param)
            if raw_val is not None:
                try:
                    val = int(raw_val)
                except (ValueError, TypeError):
                    raise ValidationError({"page_size": ["page_size must be a valid integer."]})
                if val <= 0:
                    raise ValidationError({"page_size": ["page_size must be a positive integer."]})
                if val > self.max_page_size:
                    raise ValidationError(
                        {"page_size": [f"page_size cannot exceed {self.max_page_size}."]}
                    )
                return val
        return self.page_size

    def get_page_number(self, request, paginator):
        raw_val = request.query_params.get(self.page_query_param)
        if raw_val is None:
            return 1
        if raw_val in self.last_page_strings:
            return paginator.num_pages
        try:
            val = int(raw_val)
        except (ValueError, TypeError):
            raise ValidationError({"page": ["page must be a valid integer."]})
        if val <= 0:
            raise ValidationError({"page": ["page must be a positive integer."]})
        return val
