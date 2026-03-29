from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from core.models import ObjectChange
from tenancy.models import Environment, Organization, Workspace
from users.models import Membership, ObjectPermission, User


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
        self.workspace_content_type = ContentType.objects.get_for_model(Workspace)

    def test_organization_list_is_scoped_for_members(self):
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("organization_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.organization.name)
        self.assertNotContains(response, self.other_organization.name)
        self.assertNotContains(response, "Add organization")

    def test_organization_list_renders_for_staff(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("organization_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Organizations")
        self.assertContains(response, self.organization.name)

    def test_organization_detail_includes_changelog_tab(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("organization_detail", args=[self.organization.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("organization_changelog", args=[self.organization.pk]))

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

    def test_workspace_changelog_is_scoped_for_members(self):
        self.workspace.description = "Scope-safe update"
        self.workspace.save()
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("workspace_changelog", args=[self.workspace.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Scope-safe update")

    def test_workspace_changelog_is_forbidden_outside_active_scope(self):
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("workspace_changelog", args=[self.other_workspace.pk]))

        self.assertEqual(response.status_code, 404)

    def test_organization_changelog_includes_workspace_related_changes(self):
        self.workspace.description = "Workspace updated"
        self.workspace.save()
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("organization_changelog", args=[self.organization.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.workspace.name)
        self.assertContains(response, "Workspace updated")

    def test_workspace_add_requires_explicit_add_permission(self):
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("workspace_add"))

        self.assertEqual(response.status_code, 403)

    def test_workspace_add_form_uses_scoped_choices_when_permission_granted(self):
        permission = ObjectPermission.objects.create(
            name="Scoped workspace add form",
            actions=["add"],
            constraints={"organization": "$organization"},
        )
        permission.content_types.add(self.workspace_content_type)
        self.membership.object_permissions.add(permission)
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("workspace_add"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.organization.name)
        self.assertNotContains(response, self.other_organization.name)

    def test_organization_edit_form_does_not_render_changelog_message_field(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("organization_edit", args=[self.organization.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="changelog_message"')
        self.assertNotContains(response, 'id="id_changelog_message"')

    def test_organization_edit_records_changelog_entry_without_message(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("organization_edit", args=[self.organization.pk]),
            {
                "name": self.organization.name,
                "description": "Updated tenant",
            },
        )

        self.assertEqual(response.status_code, 302)
        latest_change = ObjectChange.objects.filter(
            changed_object_id=self.organization.pk,
            action=ObjectChange.ActionChoices.UPDATE,
        ).first()
        self.assertIsNotNone(latest_change)

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
        self.assertContains(response, "Recent Changes")

    def test_home_dashboard_includes_recent_changes_panel_for_staff(self):
        self.organization.description = "Updated primary tenant"
        self.organization.save()
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Recent Changes")
        self.assertContains(response, self.organization.name)

    def test_home_dashboard_scopes_recent_changes_panel_for_members(self):
        self.workspace.description = "Scoped workspace update"
        self.workspace.save()
        self.other_workspace.description = "Other workspace update"
        self.other_workspace.save()
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Recent Changes")
        self.assertContains(response, self.workspace.name)
        self.assertNotContains(response, self.other_workspace.name)

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
