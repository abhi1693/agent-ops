from django.test import TestCase
from django.urls import reverse

from tenancy.models import Organization, Workspace
from users.models import Membership, User


class ObjectChangeListViewTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="operator",
            email="operator@example.com",
            password="correct-horse-battery-staple",
            is_staff=True,
        )
        self.scoped_user = User.objects.create_user(
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
        Membership.objects.create(
            user=self.scoped_user,
            organization=self.organization,
            workspace=self.workspace,
            is_default=True,
        )

        self.workspace.description = "Scoped UI change"
        self.workspace.save()
        self.other_workspace.description = "Hidden UI change"
        self.other_workspace.save()

    def test_staff_can_view_global_changelog_list(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(
            reverse("objectchange_list"),
            {"action": "update"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Changelog")
        self.assertContains(response, self.workspace.name)
        self.assertContains(response, self.other_workspace.name)
        self.assertContains(response, reverse("workspace_changelog", args=[self.workspace.pk]))

    def test_scoped_member_changelog_list_is_filtered(self):
        self.client.force_login(self.scoped_user)

        response = self.client.get(
            reverse("objectchange_list"),
            {"action": "update"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.workspace.name)
        self.assertNotContains(response, self.other_workspace.name)
