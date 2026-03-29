from django.test import TestCase
from django.urls import reverse

from tenancy.models import Organization, Workspace
from users.models import User


class TenancyAPITests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="operator",
            email="operator@example.com",
            password="correct-horse-battery-staple",
            is_staff=True,
        )
        self.standard_user = User.objects.create_user(
            username="viewer",
            email="viewer@example.com",
            password="correct-horse-battery-staple",
        )
        self.organization = Organization.objects.create(name="Acme", description="Primary tenant")
        self.workspace = Workspace.objects.create(
            organization=self.organization,
            name="Operations",
            description="Operational workspace",
        )

    def test_tenancy_api_root_requires_staff(self):
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("api:tenancy-api:api-root"))

        self.assertEqual(response.status_code, 403)

    def test_tenancy_api_root_lists_endpoints_for_staff(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("api:tenancy-api:api-root"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "organizations": "http://testserver/api/tenancy/organizations/",
                "workspaces": "http://testserver/api/tenancy/workspaces/",
                "environments": "http://testserver/api/tenancy/environments/",
            },
        )

    def test_environment_create_uses_workspace_scope_for_organization(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("api:tenancy-api:environment-list"),
            {
                "name": "production",
                "description": "Production environment",
                "workspace": self.workspace.pk,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["workspace"]["id"], self.workspace.pk)
        self.assertEqual(payload["organization"]["id"], self.organization.pk)
        self.assertEqual(payload["organization"]["name"], self.organization.name)
