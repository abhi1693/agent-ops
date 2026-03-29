import re
from types import SimpleNamespace

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory, TestCase
from django.urls import reverse

from core.navigation import build_navigation
from tenancy.models import Organization
from users.models import Group, Membership, ObjectPermission, Token, User


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
        self.factory = RequestFactory()
        self.organization = Organization.objects.create(name="Acme")
        self.membership = Membership.objects.create(
            user=self.user,
            organization=self.organization,
            is_default=True,
        )

    def test_home_redirects_anonymous_user_to_login(self) -> None:
        response = self.client.get(reverse("home"))

        self.assertRedirects(response, f"{reverse('login')}?next={reverse('home')}")

    def test_login_page_renders(self) -> None:
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sign in")
        self.assertContains(response, "Username or email")

    def test_base_template_uses_stored_theme_for_anonymous_users(self) -> None:
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'const useStoredTheme = true;')
        self.assertContains(response, 'const preferredTheme = "system";')
        self.assertContains(response, 'initMode();')
        self.assertNotContains(response, 'data-bs-theme="system"')

    def test_base_template_renders_explicit_dark_theme_on_root_elements(self) -> None:
        config = self.user.get_config()
        config.set("ui.theme", "dark", commit=True)
        self.client.force_login(self.user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('const useStoredTheme = false;', content)
        self.assertIn('const preferredTheme = "dark";', content)
        self.assertIn('initMode(preferredTheme);', content)
        self.assertRegex(content, r'<html[^>]*data-bs-theme="dark"')
        self.assertRegex(content, r'<body[^>]*data-bs-theme="dark"')

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

    def test_home_renders_compact_account_sections_for_authenticated_user(self) -> None:
        group = Group.objects.create(name="Operators", description="Operational staff")
        object_permission = ObjectPermission.objects.create(
            name="View active users",
            actions=["view", "change"],
        )
        object_permission.content_types.add(self.user_content_type)
        Token(user=self.user, description="CLI access").save()

        self.user.groups.add(group)
        self.user.object_permissions.add(object_permission)
        self.client.force_login(self.user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your Account")
        self.assertContains(response, "Automation")
        self.assertContains(response, "Administration")
        self.assertContains(response, "Access Relationships")
        self.assertNotContains(response, "Recent API Tokens")
        self.assertContains(response, group.name)
        self.assertContains(response, object_permission.name)

    def test_home_does_not_render_removed_staff_panels(self) -> None:
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Administration")
        self.assertNotContains(response, "Recent API Tokens")
        self.assertNotContains(response, "Newest Users")
        self.assertNotContains(response, "Access Catalog")
        self.assertContains(response, "Users")
        self.assertContains(response, "Authentication")
        self.assertContains(response, "Tenancy")
        self.assertContains(response, "Organizations")
        self.assertContains(response, "Object Permissions")

    def test_navigation_registry_excludes_account_links_from_sidebar(self) -> None:
        request = self.factory.get(reverse("home"))
        request.user = self.staff_user
        request.resolver_match = SimpleNamespace(url_name="home")

        nav_items = build_navigation(request)

        self.assertEqual(len(nav_items), 3)
        nav_by_label = {item["label"]: item for item in nav_items}
        self.assertEqual(set(nav_by_label), {"Activity", "Administration", "Tenancy"})

        activity_entries = [
            (item["label"], item["icon_class"], item["add_url"])
            for group in nav_by_label["Activity"]["groups"]
            for item in group["items"]
        ]
        self.assertEqual(
            activity_entries,
            [
                ("Changelog", "mdi mdi-history", None),
            ],
        )

        administration_entries = [
            (item["label"], item["icon_class"], item["add_url"])
            for group in nav_by_label["Administration"]["groups"]
            for item in group["items"]
        ]
        self.assertEqual(
            administration_entries,
            [
                ("Users", "mdi mdi-account-outline", reverse("user_add")),
                ("Groups", "mdi mdi-account-group-outline", reverse("group_add")),
                ("Memberships", "mdi mdi-account-key-outline", reverse("membership_add")),
                ("Object Permissions", "mdi mdi-shield-key-outline", reverse("objectpermission_add")),
            ],
        )
        tenancy_entries = [
            (item["label"], item["icon_class"], item["add_url"])
            for group in nav_by_label["Tenancy"]["groups"]
            for item in group["items"]
        ]
        self.assertEqual(
            tenancy_entries,
            [
                ("Organizations", "mdi mdi-office-building-outline", reverse("organization_add")),
                ("Workspaces", "mdi mdi-briefcase-outline", reverse("workspace_add")),
                ("Environments", "mdi mdi-cloud-outline", reverse("environment_add")),
            ],
        )
        menu_labels = [
            label for label, _icon, _add_url in [*activity_entries, *administration_entries, *tenancy_entries]
        ]
        self.assertNotIn("Profile", menu_labels)
        self.assertNotIn("Preferences", menu_labels)
        self.assertNotIn("API Tokens", menu_labels)

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
            },
        )

        self.assertRedirects(response, reverse("profile"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "alice+updated@example.com")
        self.assertEqual(self.user.first_name, "Alice")
        self.assertEqual(self.user.last_name, "Admin")

    def test_profile_edit_page_renders(self) -> None:
        self.client.force_login(self.user)

        response = self.client.get(reverse("profile_edit"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit profile")
        self.assertContains(response, "Profile")

    def test_preferences_page_renders(self) -> None:
        self.client.force_login(self.user)

        response = self.client.get(reverse("preferences"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Preferences")
        self.assertContains(response, "Save preferences")

    def test_token_create_page_renders(self) -> None:
        self.client.force_login(self.user)

        response = self.client.get(reverse("token_add"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create API token")
        self.assertContains(response, "Use active/default membership")
        self.assertNotContains(response, "Create &amp; Add Another", html=True)

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

    def test_profile_scope_update_sets_active_membership_in_session(self) -> None:
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("profile_scope"),
            {"membership": self.membership.pk},
        )

        self.assertRedirects(response, reverse("profile"))
        self.assertEqual(self.client.session["users.active_membership_id"], self.membership.pk)

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

    def test_staff_user_can_create_group_and_add_another(self) -> None:
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("group_add"),
            {
                "name": "Operators",
                "description": "Operational staff",
                "_addanother": "1",
            },
        )

        self.assertRedirects(response, reverse("group_add"))
        self.assertTrue(Group.objects.filter(name="Operators").exists())

    def test_staff_user_can_delete_group(self) -> None:
        group = Group.objects.create(name="Contractors", description="Temporary access")
        self.client.force_login(self.staff_user)

        response = self.client.post(reverse("group_delete", args=[group.pk]))

        self.assertRedirects(response, reverse("group_list"))
        self.assertFalse(Group.objects.filter(pk=group.pk).exists())

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
        self.assertContains(response, "Add user")
        self.assertContains(response, "Create &amp; Add Another", html=True)
        self.assertContains(response, "User")

    def test_staff_user_can_render_group_add_form(self) -> None:
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("group_add"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add group")
        self.assertContains(response, "Create &amp; Add Another", html=True)
        self.assertContains(response, "Permissions")

    def test_staff_user_can_render_object_permission_add_form(self) -> None:
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("objectpermission_add"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add object permission")
        self.assertContains(response, "Create &amp; Add Another", html=True)
        self.assertContains(response, "Scope")
        self.assertContains(response, "Actions")
        self.assertNotContains(response, ">null</textarea>", html=False)

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

    def test_staff_user_can_render_user_detail(self) -> None:
        group = Group.objects.create(name="Operators", description="Operational staff")
        object_permission = ObjectPermission.objects.create(name="View active users", actions=["view"])
        object_permission.content_types.add(self.user_content_type)
        token = Token(user=self.user, description="CLI access")
        token.save()
        self.user.groups.add(group)
        self.user.object_permissions.add(object_permission)
        self.user.user_permissions.add(self.change_user_permission)
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("user_detail", args=[self.user.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Access summary")
        self.assertContains(response, 'class="table table-hover attr-table mb-0"', html=False)
        self.assertContains(response, group.name)
        self.assertContains(response, object_permission.name)
        self.assertContains(response, self.change_user_permission.name)

    def test_staff_user_can_render_group_detail(self) -> None:
        group = Group.objects.create(name="Operators", description="Operational staff")
        group.permissions.add(self.change_user_permission)
        object_permission = ObjectPermission.objects.create(name="View active users", actions=["view"])
        object_permission.content_types.add(self.user_content_type)
        group.object_permissions.add(object_permission)
        group.users.add(self.user)
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("group_detail", args=[group.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Details")
        self.assertContains(response, "Summary")
        self.assertContains(response, group.description)
        self.assertContains(response, self.user.username)
        self.assertContains(response, object_permission.name)

    def test_staff_user_can_render_object_permission_detail(self) -> None:
        object_permission = ObjectPermission.objects.create(
            name="View active users",
            description="Manage active users",
            enabled=True,
            actions=["view", "change"],
            constraints={"is_active": True},
        )
        object_permission.content_types.add(self.user_content_type)
        object_permission.users.add(self.user)
        group = Group.objects.create(name="Operators", description="Operational staff")
        object_permission.groups.add(group)
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("objectpermission_detail", args=[object_permission.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Content types")
        self.assertContains(response, "Assigned users")
        self.assertContains(response, "Assigned groups")
        self.assertContains(response, object_permission.description)
        self.assertContains(response, self.user.username)
        self.assertContains(response, group.name)

    def test_logout_clears_session(self) -> None:
        self.client.force_login(self.user)

        response = self.client.post(reverse("logout"))

        self.assertRedirects(response, reverse("login"))
        self.assertNotIn("_auth_user_id", self.client.session)
