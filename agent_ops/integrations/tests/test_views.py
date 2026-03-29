from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from integrations.models import Secret
from tenancy.models import Environment, Organization, Workspace
from users.models import Membership, ObjectPermission, User


class IntegrationsViewTests(TestCase):
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

    def test_secret_list_is_scoped_for_members(self):
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("secret_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.secret.name)
        self.assertContains(response, "Environment Variable")
        self.assertNotContains(response, self.other_secret.name)

    def test_secret_detail_shows_secret_metadata(self):
        self.client.force_login(self.staff_user)

        with patch.dict("os.environ", {"GITHUB_APP_CLIENT_SECRET": "ghs_example_secret_value"}):
            response = self.client.get(reverse("secret_detail", args=[self.secret.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.secret.name)
        self.assertContains(response, "Environment Variable")
        self.assertContains(response, "ghs_example_secret_value")
        self.assertContains(response, reverse("secret_delete", args=[self.secret.pk]))
        self.assertNotContains(response, "Summary")
        self.assertNotContains(response, "Group Assignments")

    def test_secret_detail_shows_value_resolution_error(self):
        self.client.force_login(self.staff_user)

        with patch.dict("os.environ", {}, clear=True):
            response = self.client.get(reverse("secret_detail", args=[self.secret.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<span class="text-danger">Environment variable &quot;GITHUB_APP_CLIENT_SECRET&quot; is not set.</span>',
            html=True,
        )

    def test_secret_add_requires_explicit_add_permission(self):
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("secret_add"))

        self.assertEqual(response.status_code, 403)

    def test_secret_add_form_uses_scoped_choices_when_permission_granted(self):
        permission = ObjectPermission.objects.create(
            name="Scoped secret add form",
            actions=["add"],
            constraints={"organization": "$organization"},
        )
        permission.content_types.add(self.secret_content_type)
        self.membership.object_permissions.add(permission)
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("secret_add"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.organization.name)
        self.assertContains(response, self.workspace.name)
        self.assertContains(response, self.environment.name)
        self.assertNotContains(response, self.other_organization.name)
        self.assertNotContains(response, self.other_workspace.name)
        self.assertNotContains(response, self.other_environment.name)

    def test_home_dashboard_includes_integrations_summary_for_staff(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        stats_by_title = {
            section["title"]: section for section in response.context["stats"]
        }
        self.assertIn("Integrations", stats_by_title)
        integration_items = {
            item["label"]: item for item in stats_by_title["Integrations"]["items"]
        }
        self.assertEqual(integration_items["Secrets"]["count"], 2)
        self.assertFalse(integration_items["Secrets"]["disabled"])

    def test_home_dashboard_scopes_integrations_summary_for_members(self):
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        stats_by_title = {
            section["title"]: section for section in response.context["stats"]
        }
        self.assertIn("Integrations", stats_by_title)
        integration_items = {
            item["label"]: item for item in stats_by_title["Integrations"]["items"]
        }
        self.assertEqual(integration_items["Secrets"]["count"], 1)
        self.assertContains(response, "Secrets")
        self.assertNotContains(response, "Secret Groups")
        self.assertNotContains(response, "Group Assignments")
