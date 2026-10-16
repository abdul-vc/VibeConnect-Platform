"""Organizations Pagination.

Implements bounded page-number pagination with explicit validation for page_size.
"""

from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import ValidationError


class OrganizationPagination(PageNumberPagination):
    """Standardized page-number pagination for organizations catalog."""

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
