"""VibeConnect Phase 2C Subscription Domain Pagination.

Bounded page-number pagination with explicit validation for page_size and page.
"""

from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination


class SubscriptionDefaultPagination(PageNumberPagination):
    """Default pagination (page_size=20, max_page_size=100) for Subscriptions."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_page_size(self, request):
        if self.page_size_query_param:
            raw_val = request.query_params.get(self.page_size_query_param)
            if raw_val is not None:
                try:
                    val = int(raw_val)
                    if val <= 0 or val > self.max_page_size:
                        raise ValidationError(
                            {"page_size": [f"page_size must be a positive integer between 1 and {self.max_page_size}."]}
                        )
                    return val
                except (ValueError, TypeError):
                    raise ValidationError({"page_size": ["page_size must be a valid integer."]})
        return self.page_size
