from django.test import TestCase
from django.urls import reverse

from core.models import ObjectChange
from tenancy.models import Organization, Workspace
from users.models import Membership, User


class ObjectChangeAPITests(TestCase):
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

        self.workspace.description = "Scoped API change"
        self.workspace.save()
        self.other_workspace.description = "Hidden API change"
        self.other_workspace.save()

        self.scoped_change = ObjectChange.objects.get(
            changed_object_id=self.workspace.pk,
            action=ObjectChange.ActionChoices.UPDATE,
        )
        self.hidden_change = ObjectChange.objects.get(
            changed_object_id=self.other_workspace.pk,
            action=ObjectChange.ActionChoices.UPDATE,
        )

    def test_changelog_api_list_returns_global_results_for_staff(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(
            reverse("api:changelog-list"),
            {"action": ObjectChange.ActionChoices.UPDATE},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 2)
        object_reprs = {item["object_repr"] for item in payload["results"]}
        self.assertEqual(object_reprs, {self.workspace.name, self.other_workspace.name})
        self.assertNotIn("message", payload["results"][0])
        scoped_result = next(
            item for item in payload["results"] if item["object_repr"] == self.workspace.name
        )
        self.assertTrue(scoped_result["changed_object_url"].endswith(
            reverse("workspace_changelog", args=[self.workspace.pk])
        ))

    def test_changelog_api_list_is_filtered_for_scoped_members(self):
        self.client.force_login(self.scoped_user)

        response = self.client.get(
            reverse("api:changelog-list"),
            {"action": ObjectChange.ActionChoices.UPDATE},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["object_repr"], self.workspace.name)
        self.assertNotIn("message", payload["results"][0])

    def test_changelog_api_detail_hides_out_of_scope_changes(self):
        self.client.force_login(self.scoped_user)

        response = self.client.get(reverse("api:changelog-detail", args=[self.hidden_change.pk]))

        self.assertEqual(response.status_code, 404)
