from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from core.models import ObjectChange
from tenancy.models import Organization, Workspace
from users.models import User


class ObjectChangeTests(TestCase):
    def test_create_update_and_delete_record_snapshots(self):
        organization = Organization.objects.create(name="Acme")
        organization_id = organization.pk
        organization_content_type = ContentType.objects.get_for_model(
            Organization,
            for_concrete_model=False,
        )

        create_change = ObjectChange.objects.get(
            changed_object_type=organization_content_type,
            changed_object_id=organization_id,
            action=ObjectChange.ActionChoices.CREATE,
        )
        self.assertIsNone(create_change.prechange_data)
        self.assertEqual(create_change.postchange_data["name"], "Acme")

        organization.description = "Primary tenant"
        organization.save()

        update_change = ObjectChange.objects.get(
            changed_object_type=organization_content_type,
            changed_object_id=organization_id,
            action=ObjectChange.ActionChoices.UPDATE,
        )
        self.assertEqual(update_change.prechange_data["description"], "")
        self.assertEqual(update_change.postchange_data["description"], "Primary tenant")

        organization.delete()

        delete_change = ObjectChange.objects.get(
            changed_object_type=organization_content_type,
            changed_object_id=organization_id,
            action=ObjectChange.ActionChoices.DELETE,
        )
        self.assertEqual(delete_change.prechange_data["description"], "Primary tenant")
        self.assertIsNone(delete_change.postchange_data)

    def test_related_object_is_recorded_for_workspace_changes(self):
        organization = Organization.objects.create(name="Acme")
        workspace = Workspace.objects.create(
            organization=organization,
            name="Operations",
        )
        workspace_content_type = ContentType.objects.get_for_model(
            Workspace,
            for_concrete_model=False,
        )
        organization_content_type = ContentType.objects.get_for_model(
            Organization,
            for_concrete_model=False,
        )

        change = ObjectChange.objects.get(
            changed_object_type=workspace_content_type,
            changed_object_id=workspace.pk,
            action=ObjectChange.ActionChoices.CREATE,
        )

        self.assertEqual(change.related_object_type, organization_content_type)
        self.assertEqual(change.related_object_id, organization.pk)

    def test_user_changelog_excludes_sensitive_fields(self):
        user = User.objects.create_user(
            username="audited-user",
            email="audited-user@example.com",
            password="correct-horse-battery-staple",
        )
        user_content_type = ContentType.objects.get_for_model(
            User,
            for_concrete_model=False,
        )

        change = ObjectChange.objects.get(
            changed_object_type=user_content_type,
            changed_object_id=user.pk,
            action=ObjectChange.ActionChoices.CREATE,
        )

        self.assertNotIn("password", change.postchange_data)
        self.assertNotIn("last_login", change.postchange_data)
