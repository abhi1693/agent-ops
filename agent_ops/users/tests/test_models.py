from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models import ChangeLoggedModel, OrganizationalModel, PrimaryModel
from tenancy.models import Environment, Organization, Workspace
from users.models import Group, Membership, ObjectPermission, Token, User, UserConfig


class ModelInheritanceTests(TestCase):
    def test_group_inherits_organizational_model(self) -> None:
        self.assertTrue(issubclass(Group, OrganizationalModel))
        self.assertEqual(Group._meta.get_field("name").max_length, 150)
        self.assertEqual(Group._meta.get_field("description").max_length, 200)

    def test_object_permission_inherits_organizational_model_with_name_override(self) -> None:
        self.assertTrue(issubclass(ObjectPermission, OrganizationalModel))
        self.assertEqual(ObjectPermission._meta.get_field("name").max_length, 100)
        self.assertEqual(ObjectPermission._meta.get_field("description").max_length, 200)

    def test_token_inherits_primary_model(self) -> None:
        self.assertTrue(issubclass(Token, PrimaryModel))
        self.assertEqual(Token._meta.get_field("description").max_length, 200)

    def test_membership_inherits_primary_model(self) -> None:
        self.assertTrue(issubclass(Membership, PrimaryModel))
        self.assertEqual(Membership._meta.get_field("description").max_length, 200)

    def test_user_config_inherits_change_logged_model(self) -> None:
        self.assertTrue(issubclass(UserConfig, ChangeLoggedModel))

    def test_organizational_model_string_representation_comes_from_base_class(self) -> None:
        group = Group(name="Operators")
        permission = ObjectPermission(name="View users", actions=["view"])

        self.assertEqual(str(group), "Operators")
        self.assertEqual(str(permission), "View users")

    def test_user_model_remains_concrete_custom_auth_model(self) -> None:
        self.assertFalse(issubclass(User, OrganizationalModel))
        self.assertEqual(User.USERNAME_FIELD, "username")


class MembershipModelTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="scope-user",
            email="scope-user@example.com",
            password="testpass123",
        )
        self.organization = Organization.objects.create(name="Acme")
        self.workspace = Workspace.objects.create(
            organization=self.organization,
            name="Operations",
        )
        self.environment = Environment.objects.create(
            workspace=self.workspace,
            name="production",
        )

    def test_membership_derives_parent_scope_from_environment(self) -> None:
        membership = Membership(
            user=self.user,
            organization=self.organization,
            environment=self.environment,
        )

        membership.full_clean()

        self.assertEqual(membership.workspace, self.workspace)
        self.assertEqual(membership.organization, self.organization)

    def test_membership_prevents_duplicate_scope_for_same_user(self) -> None:
        Membership.objects.create(
            user=self.user,
            organization=self.organization,
            workspace=self.workspace,
        )
        duplicate = Membership(
            user=self.user,
            organization=self.organization,
            workspace=self.workspace,
        )

        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_first_active_membership_becomes_default(self) -> None:
        membership = Membership.objects.create(
            user=self.user,
            organization=self.organization,
        )

        self.assertTrue(membership.is_default)

    def test_token_scope_membership_must_belong_to_token_user(self) -> None:
        membership = Membership.objects.create(
            user=self.user,
            organization=self.organization,
        )
        other_user = User.objects.create_user(
            username="other-user",
            email="other@example.com",
            password="testpass123",
        )
        token = Token(user=other_user, description="Scoped token", scope_membership=membership)

        with self.assertRaises(ValidationError):
            token.full_clean()
