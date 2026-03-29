from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from tenancy.models import Organization, Workspace
from users.models import Membership, ObjectPermission, Token, User


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
        self.workspace_content_type = ContentType.objects.get_for_model(Workspace)

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

    def test_scoped_member_cannot_create_workspace_without_add_permission(self):
        self.client.force_login(self.standard_user)

        response = self.client.post(
            reverse("api:tenancy-api:workspace-list"),
            {
                "organization": self.organization.pk,
                "name": "Analytics",
                "description": "Analytics workspace",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_scoped_member_can_create_workspace_with_add_permission(self):
        permission = ObjectPermission.objects.create(
            name="Scoped workspace add",
            actions=["add"],
            constraints={"organization": "$organization"},
        )
        permission.content_types.add(self.workspace_content_type)
        self.membership.object_permissions.add(permission)
        self.client.force_login(self.standard_user)

        response = self.client.post(
            reverse("api:tenancy-api:workspace-list"),
            {
                "organization": self.organization.pk,
                "name": "Analytics",
                "description": "Analytics workspace",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["organization"]["id"], self.organization.pk)
        self.assertTrue(
            Workspace.objects.filter(
                organization=self.organization,
                name="Analytics",
            ).exists()
        )

    def test_scoped_member_cannot_create_workspace_outside_permission_scope(self):
        permission = ObjectPermission.objects.create(
            name="Scoped workspace add outside",
            actions=["add"],
            constraints={"organization": "$organization"},
        )
        permission.content_types.add(self.workspace_content_type)
        self.membership.object_permissions.add(permission)
        self.client.force_login(self.standard_user)

        response = self.client.post(
            reverse("api:tenancy-api:workspace-list"),
            {
                "organization": self.other_organization.pk,
                "name": "Security Analytics",
                "description": "Should fail",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            Workspace.objects.filter(
                organization=self.other_organization,
                name="Security Analytics",
            ).exists()
        )

    def test_scoped_member_can_update_workspace_with_change_permission(self):
        permission = ObjectPermission.objects.create(
            name="Scoped workspace change",
            actions=["change"],
            constraints={"organization": "$organization"},
        )
        permission.content_types.add(self.workspace_content_type)
        self.membership.object_permissions.add(permission)
        self.client.force_login(self.standard_user)

        response = self.client.patch(
            reverse("api:tenancy-api:workspace-detail", args=[self.workspace.pk]),
            {
                "organization": self.organization.pk,
                "name": self.workspace.name,
                "description": "Updated description",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.description, "Updated description")

    def test_scoped_member_change_is_rejected_when_object_moves_outside_scope(self):
        permission = ObjectPermission.objects.create(
            name="Scoped workspace change outside",
            actions=["change"],
            constraints={"organization": "$organization"},
        )
        permission.content_types.add(self.workspace_content_type)
        self.membership.object_permissions.add(permission)
        self.client.force_login(self.standard_user)

        response = self.client.patch(
            reverse("api:tenancy-api:workspace-detail", args=[self.workspace.pk]),
            {
                "organization": self.other_organization.pk,
                "name": self.workspace.name,
                "description": "Attempted move",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.organization, self.organization)
        self.assertNotEqual(self.workspace.description, "Attempted move")

    def test_scoped_member_change_is_revalidated_after_save(self):
        permission = ObjectPermission.objects.create(
            name="Scoped workspace change by name",
            actions=["change"],
            constraints={
                "organization": "$organization",
                "name": "Operations",
            },
        )
        permission.content_types.add(self.workspace_content_type)
        self.membership.object_permissions.add(permission)
        self.client.force_login(self.standard_user)

        response = self.client.patch(
            reverse("api:tenancy-api:workspace-detail", args=[self.workspace.pk]),
            {
                "organization": self.organization.pk,
                "name": "Operations Renamed",
                "description": self.workspace.description,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.name, "Operations")
