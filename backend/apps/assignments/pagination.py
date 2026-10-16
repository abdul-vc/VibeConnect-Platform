"""Pagination for Assignment Domain APIs."""

from rest_framework.pagination import PageNumberPagination


class AssignmentPagination(PageNumberPagination):
    """Standard pagination for assignment listings and member selector."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
