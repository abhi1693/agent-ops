from django.test import TestCase
from django.urls import reverse

from tenancy.models import Environment, Organization, Workspace
from users.models import User


class TenancyViewTests(TestCase):
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

    def test_organization_list_requires_staff(self):
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("organization_list"))

        self.assertEqual(response.status_code, 403)

    def test_organization_list_renders_for_staff(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("organization_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Organizations")
        self.assertContains(response, self.organization.name)

    def test_workspace_detail_shows_related_environments(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("workspace_detail", args=[self.workspace.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.workspace.name)
        self.assertContains(response, self.environment.name)
        self.assertContains(response, self.organization.name)

    def test_home_dashboard_includes_tenancy_summary_for_staff(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        stats_by_title = {
            section["title"]: section for section in response.context["stats"]
        }
        self.assertIn("Tenancy", stats_by_title)
        tenancy_items = {
            item["label"]: item for item in stats_by_title["Tenancy"]["items"]
        }
        self.assertEqual(tenancy_items["Organizations"]["count"], 1)
        self.assertEqual(tenancy_items["Workspaces"]["count"], 1)
        self.assertEqual(tenancy_items["Environments"]["count"], 1)
        self.assertFalse(response.context["dashboard_panels"])

    def test_home_dashboard_omits_tenancy_summary_for_non_staff(self):
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        stat_titles = {section["title"] for section in response.context["stats"]}
        self.assertNotIn("Tenancy", stat_titles)
        self.assertNotContains(response, "Tenant Scope")
