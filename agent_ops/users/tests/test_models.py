from django.test import TestCase

from core.models import ChangeLoggedModel, OrganizationalModel, PrimaryModel
from users.models import Group, ObjectPermission, Token, User, UserConfig


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
