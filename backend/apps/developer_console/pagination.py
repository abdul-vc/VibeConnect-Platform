from rest_framework.pagination import PageNumberPagination


class DeveloperApiPagination(PageNumberPagination):
    """Standard pagination for Developer API collections (default 25, max 100)."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
