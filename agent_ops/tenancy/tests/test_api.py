from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from tenancy.models import Organization, Workspace
from users.models import Membership, Token, User


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
        self.other_organization = Organization.objects.create(name="Beta", description="Secondary tenant")
        self.other_workspace = Workspace.objects.create(
            organization=self.other_organization,
            name="Security",
            description="Security workspace",
        )
        self.membership = Membership.objects.create(
            user=self.standard_user,
            organization=self.organization,
            workspace=self.workspace,
            is_default=True,
        )

    def test_tenancy_api_root_is_available_for_scoped_members(self):
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("api:tenancy-api:api-root"))

        self.assertEqual(response.status_code, 200)

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

    def test_scoped_member_only_lists_objects_inside_active_scope(self):
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("api:tenancy-api:workspace-list"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["id"], self.workspace.id)

    def test_scoped_token_filters_tenancy_results(self):
        token = Token(
            user=self.standard_user,
            description="Scoped tenant token",
            scope_membership=self.membership,
        )
        token.save()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.plaintext_token}")

        response = client.get(reverse("api:tenancy-api:organization-list"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["id"], self.organization.id)
