from django.test import TestCase
from django.urls import reverse

from tenancy.models import Environment, Organization, Workspace
from users.models import Membership, User


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

    def test_organization_list_is_scoped_for_members(self):
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("organization_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.organization.name)
        self.assertNotContains(response, self.other_organization.name)

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

    def test_workspace_detail_is_forbidden_outside_active_scope(self):
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("workspace_detail", args=[self.other_workspace.pk]))

        self.assertEqual(response.status_code, 404)

    def test_member_home_dashboard_includes_scoped_tenancy_summary(self):
        self.client.force_login(self.standard_user)

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
        self.assertEqual(tenancy_items["Organizations"]["count"], 2)
        self.assertEqual(tenancy_items["Workspaces"]["count"], 2)
        self.assertEqual(tenancy_items["Environments"]["count"], 2)
        self.assertFalse(response.context["dashboard_panels"])

    def test_home_dashboard_omits_tenancy_summary_for_non_staff(self):
        unscoped_user = User.objects.create_user(
            username="no-scope",
            email="no-scope@example.com",
            password="correct-horse-battery-staple",
        )
        self.client.force_login(unscoped_user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        stat_titles = {section["title"] for section in response.context["stats"]}
        self.assertNotIn("Tenancy", stat_titles)
        self.assertNotContains(response, "Tenant Scope")
