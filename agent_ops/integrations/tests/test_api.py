from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from integrations.models import Secret, SecretGroup, SecretGroupAssignment
from tenancy.models import Environment, Organization, Workspace
from users.models import Membership, ObjectPermission, User


class IntegrationsAPITests(TestCase):
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
        self.environment = Environment.objects.create(
            workspace=self.workspace,
            name="production",
            description="Production environment",
        )
        self.other_organization = Organization.objects.create(name="Beta", description="Secondary tenant")
        self.other_workspace = Workspace.objects.create(
            organization=self.other_organization,
            name="Security",
            description="Security workspace",
        )
        self.other_environment = Environment.objects.create(
            workspace=self.other_workspace,
            name="staging",
            description="Staging environment",
        )
        self.membership = Membership.objects.create(
            user=self.standard_user,
            organization=self.organization,
            workspace=self.workspace,
            is_default=True,
        )
        self.secret_content_type = ContentType.objects.get_for_model(Secret)
        self.secret_group_content_type = ContentType.objects.get_for_model(SecretGroup)
        self.secret_group_assignment_content_type = ContentType.objects.get_for_model(SecretGroupAssignment)
        self.secret = Secret.objects.create(
            provider="environment-variable",
            environment=self.environment,
            name="github-app-client-secret",
            parameters={"variable": "GITHUB_APP_CLIENT_SECRET"},
        )
        self.other_secret = Secret.objects.create(
            provider="environment-variable",
            environment=self.other_environment,
            name="slack-bot-token",
            parameters={"variable": "SLACK_BOT_TOKEN"},
        )
        self.secret_group = SecretGroup.objects.create(
            environment=self.environment,
            name="github-production",
            description="GitHub production credentials",
        )
        self.other_secret_group = SecretGroup.objects.create(
            environment=self.other_environment,
            name="slack-staging",
            description="Slack staging credentials",
        )
        self.secret_group_assignment = SecretGroupAssignment.objects.create(
            secret_group=self.secret_group,
            secret=self.secret,
            key="client-secret",
            required=True,
            order=10,
        )

    def test_integrations_api_root_is_available_for_scoped_members(self):
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("api:integrations-api:api-root"))

        self.assertEqual(response.status_code, 200)

    def test_integrations_api_root_lists_endpoints_for_staff(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("api:integrations-api:api-root"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "secrets": "http://testserver/api/integrations/secrets/",
                "secret-groups": "http://testserver/api/integrations/secret-groups/",
                "secret-group-assignments": "http://testserver/api/integrations/secret-group-assignments/",
            },
        )

    def test_secret_create_derives_scope_from_environment(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("api:integrations-api:secret-list"),
            {
                "environment": self.environment.pk,
                "name": "github-webhook-secret",
                "description": "Webhook verifier",
                "provider": "environment-variable",
                "parameters": {"variable": "GITHUB_WEBHOOK_SECRET"},
                "metadata": {"category": "webhook"},
                "enabled": True,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["environment"]["id"], self.environment.pk)
        self.assertEqual(payload["workspace"]["id"], self.workspace.pk)
        self.assertEqual(payload["organization"]["id"], self.organization.pk)
        self.assertEqual(payload["provider_display"], "Environment Variable")

    def test_scoped_member_only_lists_secrets_inside_active_scope(self):
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("api:integrations-api:secret-list"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["id"], self.secret.id)

    def test_secret_group_create_derives_scope_from_environment(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("api:integrations-api:secretgroup-list"),
            {
                "environment": self.environment.pk,
                "name": "github-shared",
                "description": "Shared GitHub credentials",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["environment"]["id"], self.environment.pk)
        self.assertEqual(payload["workspace"]["id"], self.workspace.pk)
        self.assertEqual(payload["organization"]["id"], self.organization.pk)

    def test_scoped_member_only_lists_secret_groups_inside_active_scope(self):
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("api:integrations-api:secretgroup-list"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["id"], self.secret_group.id)

    def test_secret_group_assignment_create_links_secret_to_group(self):
        self.client.force_login(self.staff_user)
        other_secret = Secret.objects.create(
            provider="environment-variable",
            environment=self.environment,
            name="github-webhook-secret",
            parameters={"variable": "GITHUB_WEBHOOK_SECRET"},
        )

        response = self.client.post(
            reverse("api:integrations-api:secretgroupassignment-list"),
            {
                "secret_group": self.secret_group.pk,
                "secret": other_secret.pk,
                "key": "webhook-secret",
                "required": False,
                "order": 20,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["secret_group"]["id"], self.secret_group.pk)
        self.assertEqual(payload["secret"]["id"], other_secret.pk)
        self.assertEqual(payload["organization"]["id"], self.organization.pk)
        self.assertEqual(payload["workspace"]["id"], self.workspace.pk)
        self.assertEqual(payload["environment"]["id"], self.environment.pk)

    def test_scoped_member_only_lists_secret_group_assignments_inside_active_scope(self):
        SecretGroupAssignment.objects.create(
            secret_group=self.other_secret_group,
            secret=self.other_secret,
            key="bot-token",
        )
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("api:integrations-api:secretgroupassignment-list"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["id"], self.secret_group_assignment.id)

    def test_scoped_member_cannot_create_secret_without_add_permission(self):
        self.client.force_login(self.standard_user)

        response = self.client.post(
            reverse("api:integrations-api:secret-list"),
            {
                "organization": self.organization.pk,
                "name": "shared-token",
                "provider": "environment-variable",
                "parameters": {"variable": "SHARED_TOKEN"},
                "metadata": {},
                "enabled": True,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_scoped_member_can_create_secret_with_add_permission(self):
        permission = ObjectPermission.objects.create(
            name="Scoped secret add",
            actions=["add"],
            constraints={"organization": "$organization"},
        )
        permission.content_types.add(self.secret_content_type)
        self.membership.object_permissions.add(permission)
        self.client.force_login(self.standard_user)

        response = self.client.post(
            reverse("api:integrations-api:secret-list"),
            {
                "organization": self.organization.pk,
                "name": "shared-token",
                "provider": "environment-variable",
                "parameters": {"variable": "SHARED_TOKEN"},
                "metadata": {"category": "shared"},
                "enabled": True,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["organization"]["id"], self.organization.pk)
        self.assertTrue(
            Secret.objects.filter(
                organization=self.organization,
                name="shared-token",
                provider="environment-variable",
            ).exists()
        )

    def test_scoped_member_cannot_create_secret_group_without_add_permission(self):
        self.client.force_login(self.standard_user)

        response = self.client.post(
            reverse("api:integrations-api:secretgroup-list"),
            {
                "organization": self.organization.pk,
                "name": "shared-platform",
                "description": "Shared integration credentials",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_scoped_member_can_create_secret_group_with_add_permission(self):
        permission = ObjectPermission.objects.create(
            name="Scoped secret group add",
            actions=["add"],
            constraints={"organization": "$organization"},
        )
        permission.content_types.add(self.secret_group_content_type)
        self.membership.object_permissions.add(permission)
        self.client.force_login(self.standard_user)

        response = self.client.post(
            reverse("api:integrations-api:secretgroup-list"),
            {
                "organization": self.organization.pk,
                "name": "shared-platform",
                "description": "Shared integration credentials",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["organization"]["id"], self.organization.pk)
        self.assertTrue(
            SecretGroup.objects.filter(
                organization=self.organization,
                name="shared-platform",
            ).exists()
        )

    def test_scoped_member_cannot_create_secret_group_assignment_without_add_permission(self):
        self.client.force_login(self.standard_user)

        response = self.client.post(
            reverse("api:integrations-api:secretgroupassignment-list"),
            {
                "secret_group": self.secret_group.pk,
                "secret": self.secret.pk,
                "key": "duplicate-client-secret",
                "required": True,
                "order": 30,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_scoped_member_can_create_secret_group_assignment_with_add_permission(self):
        permission = ObjectPermission.objects.create(
            name="Scoped secret group assignment add",
            actions=["add"],
            constraints={"organization": "$organization"},
        )
        permission.content_types.add(self.secret_group_assignment_content_type)
        self.membership.object_permissions.add(permission)
        self.client.force_login(self.standard_user)
        other_secret = Secret.objects.create(
            provider="environment-variable",
            environment=self.environment,
            name="github-webhook-secret",
            parameters={"variable": "GITHUB_WEBHOOK_SECRET"},
        )

        response = self.client.post(
            reverse("api:integrations-api:secretgroupassignment-list"),
            {
                "secret_group": self.secret_group.pk,
                "secret": other_secret.pk,
                "key": "webhook-secret",
                "required": False,
                "order": 20,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            SecretGroupAssignment.objects.filter(
                secret_group=self.secret_group,
                secret=other_secret,
                key="webhook-secret",
            ).exists()
        )

    def test_assignment_rejects_cross_scope_secret(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("api:integrations-api:secretgroupassignment-list"),
            {
                "secret_group": self.secret_group.pk,
                "secret": self.other_secret.pk,
                "key": "cross-scope-secret",
                "required": True,
                "order": 50,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
