import re

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from users.models import Group, ObjectPermission, Token, User


class AuthViewTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="alice",
            email="alice@example.com",
            password="correct-horse-battery-staple",
        )
        self.staff_user = User.objects.create_user(
            username="operator",
            email="operator@example.com",
            password="correct-horse-battery-staple",
            is_staff=True,
        )
        self.user_content_type = ContentType.objects.get_for_model(User)
        self.change_user_permission = Permission.objects.get(
            content_type=self.user_content_type,
            codename="change_user",
        )

    def test_home_redirects_anonymous_user_to_login(self) -> None:
        response = self.client.get(reverse("home"))

        self.assertRedirects(response, f"{reverse('login')}?next={reverse('home')}")

    def test_login_page_renders(self) -> None:
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sign in")
        self.assertContains(response, "Username or email")

    def test_authenticated_user_visiting_login_redirects_home(self) -> None:
        self.client.force_login(self.user)

        response = self.client.get(reverse("login"))

        self.assertRedirects(response, reverse("home"))

    def test_login_authenticates_and_redirects_home(self) -> None:
        response = self.client.post(
            reverse("login"),
            {
                "username": "alice",
                "password": "correct-horse-battery-staple",
            },
        )

        self.assertRedirects(response, reverse("home"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_login_accepts_email_address(self) -> None:
        response = self.client.post(
            reverse("login"),
            {
                "username": "alice@example.com",
                "password": "correct-horse-battery-staple",
            },
        )

        self.assertRedirects(response, reverse("home"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_invalid_login_shows_error(self) -> None:
        response = self.client.post(
            reverse("login"),
            {
                "username": "alice",
                "password": "wrong-password",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please enter a correct username and password.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_home_renders_netbox_style_sections_for_authenticated_user(self) -> None:
        group = Group.objects.create(name="Operators", description="Operational staff")
        object_permission = ObjectPermission.objects.create(
            name="View active users",
            actions=["view", "change"],
        )
        object_permission.content_types.add(self.user_content_type)
        token = Token(user=self.user, description="CLI access")
        token.save()

        self.user.groups.add(group)
        self.user.object_permissions.add(object_permission)
        self.client.force_login(self.user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your Account")
        self.assertContains(response, "Automation")
        self.assertContains(response, "Administration")
        self.assertContains(response, "Recent API Tokens")
        self.assertContains(response, "Access Relationships")
        self.assertContains(response, token.description)
        self.assertContains(response, group.name)
        self.assertContains(response, object_permission.name)

    def test_home_renders_staff_catalog_sections(self) -> None:
        group = Group.objects.create(name="Operators", description="Operational staff")
        group.users.add(self.user)

        object_permission = ObjectPermission.objects.create(
            name="Manage active users",
            actions=["view", "change"],
        )
        object_permission.content_types.add(self.user_content_type)

        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Newest Users")
        self.assertContains(response, "Access Catalog")
        self.assertContains(response, group.name)
        self.assertContains(response, object_permission.name)
        self.assertContains(response, "alice@example.com")

    def test_user_config_is_created_automatically(self) -> None:
        config = self.user.get_config()
        self.assertEqual(config.get("ui.theme"), "system")
        self.assertEqual(config.get("ui.page_size"), 50)
        self.assertEqual(config.get("ui.landing_page"), "/")

    def test_home_recreates_missing_user_config(self) -> None:
        self.user.get_config().delete()
        self.client.force_login(self.user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.user.__class__.objects.get(pk=self.user.pk).config)

    def test_profile_update_persists_first_party_user_fields(self) -> None:
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("profile_edit"),
            {
                "email": "alice+updated@example.com",
                "first_name": "Alice",
                "last_name": "Admin",
                "display_name": "Alice A.",
            },
        )

        self.assertRedirects(response, reverse("profile"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "alice+updated@example.com")
        self.assertEqual(self.user.first_name, "Alice")
        self.assertEqual(self.user.display_name, "Alice A.")

    def test_profile_edit_page_renders(self) -> None:
        self.client.force_login(self.user)

        response = self.client.get(reverse("profile_edit"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit profile")

    def test_token_list_page_renders(self) -> None:
        self.client.force_login(self.user)

        response = self.client.get(reverse("token_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "API Tokens")

    def test_preferences_update_persists_json_configuration(self) -> None:
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("preferences"),
            {
                "theme": "dark",
                "page_size": 100,
                "landing_page": "/tokens/",
            },
        )

        self.assertRedirects(response, reverse("profile"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.config.get("ui.theme"), "dark")
        self.assertEqual(self.user.config.get("ui.page_size"), 100)
        self.assertEqual(self.user.config.get("ui.landing_page"), "/tokens/")

    def test_token_create_view_issues_hashed_token(self) -> None:
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("token_add"),
            {
                "description": "CLI access",
                "enabled": "on",
                "write_enabled": "on",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "API token created.")
        token = Token.objects.get(user=self.user)
        self.assertEqual(token.description, "CLI access")
        self.assertNotEqual(token.digest, "")
        self.assertEqual(len(token.key), 12)

        match = re.search(r"agt_[A-Za-z0-9]{12}\.[A-Za-z0-9]{40}", response.content.decode())
        self.assertIsNotNone(match)
        self.assertTrue(token.validate(match.group(0)))

    def test_token_delete_view_removes_token(self) -> None:
        self.client.force_login(self.user)
        token = Token(user=self.user, description="Disposable")
        token.save()

        response = self.client.post(reverse("token_delete", args=[token.pk]))

        self.assertRedirects(response, reverse("token_list"))
        self.assertFalse(Token.objects.filter(pk=token.pk).exists())

    def test_non_staff_user_cannot_access_user_directory(self) -> None:
        self.client.force_login(self.user)

        response = self.client.get(reverse("user_list"))

        self.assertEqual(response.status_code, 403)

    def test_staff_user_can_create_object_permission(self) -> None:
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("objectpermission_add"),
            {
                "name": "Active users",
                "description": "Manage active users",
                "enabled": "on",
                "content_types": [self.user_content_type.pk],
                "actions": ["view", "change"],
                "constraints": '{"is_active": true}',
            },
        )

        permission = ObjectPermission.objects.get(name="Active users")
        self.assertRedirects(response, reverse("objectpermission_detail", args=[permission.pk]))
        self.assertEqual(permission.actions, ["view", "change"])
        self.assertEqual(permission.constraints, {"is_active": True})
        self.assertEqual(permission.content_types.get(), self.user_content_type)

    def test_staff_user_can_create_group(self) -> None:
        object_permission = ObjectPermission.objects.create(
            name="View active users",
            actions=["view"],
        )
        object_permission.content_types.add(self.user_content_type)
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("group_add"),
            {
                "name": "Operators",
                "description": "Operational staff",
                "permissions": [self.change_user_permission.pk],
                "object_permissions": [object_permission.pk],
            },
        )

        group = Group.objects.get(name="Operators")
        self.assertRedirects(response, reverse("group_detail", args=[group.pk]))
        self.assertEqual(group.permissions.get(), self.change_user_permission)
        self.assertEqual(group.object_permissions.get(), object_permission)

    def test_staff_user_can_create_platform_user(self) -> None:
        group = Group.objects.create(name="Operators")
        object_permission = ObjectPermission.objects.create(
            name="View users",
            actions=["view"],
        )
        object_permission.content_types.add(self.user_content_type)
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("user_add"),
            {
                "username": "bob",
                "email": "bob@example.com",
                "first_name": "Bob",
                "last_name": "Builder",
                "display_name": "Builder Bob",
                "is_active": "on",
                "is_staff": "on",
                "groups": [group.pk],
                "object_permissions": [object_permission.pk],
                "user_permissions": [self.change_user_permission.pk],
                "password1": "another-correct-horse-battery-staple",
                "password2": "another-correct-horse-battery-staple",
            },
        )

        user = User.objects.get(username="bob")
        self.assertRedirects(response, reverse("user_detail", args=[user.pk]))
        self.assertEqual(user.email, "bob@example.com")
        self.assertTrue(user.groups.filter(pk=group.pk).exists())
        self.assertTrue(user.object_permissions.filter(pk=object_permission.pk).exists())
        self.assertTrue(user.user_permissions.filter(pk=self.change_user_permission.pk).exists())

    def test_staff_user_can_render_user_add_form(self) -> None:
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("user_add"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create user")

    def test_staff_user_can_render_user_directory(self) -> None:
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("user_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Users")

    def test_staff_user_can_render_group_directory(self) -> None:
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("group_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Groups")

    def test_staff_user_can_render_object_permission_directory(self) -> None:
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("objectpermission_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Object Permissions")

    def test_logout_clears_session(self) -> None:
        self.client.force_login(self.user)

        response = self.client.post(reverse("logout"))

        self.assertRedirects(response, reverse("login"))
        self.assertNotIn("_auth_user_id", self.client.session)
