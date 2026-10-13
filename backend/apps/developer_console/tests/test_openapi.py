from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient


class DeveloperOpenApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_schema_endpoint_accessible_and_scoped_to_developer_apis_only(self):
        """Verify GET /api/v1/developer/schema/ returns OpenAPI 3.0 specification covering ONLY developer endpoints."""
        response = self.client.get("/api/v1/developer/schema/?format=json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        schema = response.json()

        self.assertIn("openapi", schema)
        self.assertIn("paths", schema)
        paths = schema["paths"]

        # Exactly the four developer endpoints must be present
        self.assertIn("/api/v1/developer/catalog/products/", paths)
        self.assertIn("/api/v1/developer/organization/", paths)
        self.assertIn("/api/v1/developer/entitlements/", paths)
        self.assertIn("/api/v1/developer/assignments/", paths)

        # Prohibited/internal endpoints must NOT be present
        for path in paths.keys():
            self.assertTrue(
                path.startswith("/api/v1/developer/"),
                f"Prohibited non-developer path found in schema: {path}",
            )
            self.assertFalse(path.startswith("/api/v1/auth/"))
            self.assertFalse(path.startswith("/api/v1/tenant/"))
            self.assertFalse(path.startswith("/api/v1/owner/"))
            self.assertFalse(path.startswith("/api/v1/marketplace/"))
            self.assertFalse(path.startswith("/api/v1/integration/"))

        # Verify security scheme
        security_schemes = schema.get("components", {}).get("securitySchemes", {})
        self.assertIn("DeveloperApiKeyAuth", security_schemes)
        self.assertEqual(security_schemes["DeveloperApiKeyAuth"]["type"], "http")
        self.assertEqual(security_schemes["DeveloperApiKeyAuth"]["scheme"], "bearer")

    def test_docs_endpoint_accessible(self):
        """Verify GET /api/v1/developer/docs/ returns 200 HTML documentation view."""
        response = self.client.get("/api/v1/developer/docs/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("text/html", response["Content-Type"])
        self.assertIn(b"swagger", response.content.lower())
