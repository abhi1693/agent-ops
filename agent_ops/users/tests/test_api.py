from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from tenancy.models import Organization
from users.models import Group, Membership, ObjectPermission, Token, User


class APITestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="api-user",
            email="api-user@example.com",
            password="testpass123",
            first_name="API",
            last_name="User",
            display_name="API User",
        )
        cls.staff_user = User.objects.create_user(
            username="staff-user",
            email="staff-user@example.com",
            password="testpass123",
            is_staff=True,
        )
        cls.other_user = User.objects.create_user(
            username="other-user",
            email="other-user@example.com",
            password="testpass123",
        )
        cls.group = Group.objects.create(name="Operators", description="Operations team")
        cls.user_content_type = ContentType.objects.get_for_model(User)
        cls.permission = Permission.objects.get(
            content_type=cls.user_content_type,
            codename="view_user",
        )
        cls.object_permission = ObjectPermission.objects.create(
            name="View users",
            description="View user records",
            enabled=True,
            actions=["view"],
        )
        cls.object_permission.content_types.add(cls.user_content_type)
        cls.group.permissions.add(cls.permission)
        cls.group.object_permissions.add(cls.object_permission)
        cls.user.groups.add(cls.group)
        cls.user.user_permissions.add(cls.permission)
        cls.user.object_permissions.add(cls.object_permission)
        cls.organization = Organization.objects.create(name="Acme", description="Tenant")
        cls.membership = Membership.objects.create(
            user=cls.user,
            organization=cls.organization,
            is_default=True,
        )

    def test_api_root_requires_authentication(self):
        response = self.client.get(reverse("api:api-root"))

        self.assertEqual(response.status_code, 403)

    def test_api_root_lists_top_level_endpoints(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("api:api-root"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "changelog": "http://testserver/api/changelog/",
                "tenancy": "http://testserver/api/tenancy/",
                "users": "http://testserver/api/users/",
                "status": "http://testserver/api/status/",
            },
        )

    def test_api_status_is_public(self):
        response = self.client.get(reverse("api:status"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["hostname"], settings.HOSTNAME)
        self.assertIn("users", response.json()["installed_apps"])

    def test_api_schema_requires_authentication(self):
        response = self.client.get(reverse("api:schema"))

        self.assertEqual(response.status_code, 403)

    def test_api_schema_is_available_when_authenticated(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("api:schema"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("openapi:", response.content.decode())

    def test_users_api_root_lists_registered_endpoints(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("api:users-api:api-root"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "users": "http://testserver/api/users/users/",
                "groups": "http://testserver/api/users/groups/",
                "memberships": "http://testserver/api/users/memberships/",
                "permissions": "http://testserver/api/users/permissions/",
                "tokens": "http://testserver/api/users/tokens/",
                "config": "http://testserver/api/users/config/",
            },
        )

    def test_user_list_endpoint_requires_staff(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("api:users-api:user-list"))

        self.assertEqual(response.status_code, 403)

    def test_user_list_endpoint_returns_paginated_results_for_staff(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("api:users-api:user-list"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 3)
        usernames = {result["username"] for result in payload["results"]}
        self.assertEqual(usernames, {self.user.username, self.staff_user.username, self.other_user.username})
        result = next(item for item in payload["results"] if item["username"] == self.user.username)
        self.assertEqual(result["groups"], [{"id": self.group.id, "name": self.group.name, "description": self.group.description}])
        self.assertEqual(
            result["object_permissions"],
            [
                {
                    "id": self.object_permission.id,
                    "name": self.object_permission.name,
                    "description": self.object_permission.description,
                    "enabled": True,
                    "actions": ["view"],
                }
            ],
        )
        self.assertEqual(
            result["user_permissions"],
            [
                {
                    "id": self.permission.id,
                    "name": self.permission.name,
                    "codename": self.permission.codename,
                    "content_type": {
                        "id": self.user_content_type.id,
                        "app_label": self.user_content_type.app_label,
                        "model": self.user_content_type.model,
                    },
                }
            ],
        )

    def test_user_create_accepts_primary_keys_for_related_fields(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("api:users-api:user-list"),
            {
                "username": "nested-user",
                "email": "nested-user@example.com",
                "password": "testpass123",
                "groups": [self.group.id],
                "object_permissions": [self.object_permission.id],
                "user_permissions": [self.permission.id],
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(
            payload["groups"],
            [{"id": self.group.id, "name": self.group.name, "description": self.group.description}],
        )
        self.assertEqual(payload["object_permissions"][0]["id"], self.object_permission.id)
        self.assertEqual(payload["user_permissions"][0]["id"], self.permission.id)

    def test_user_list_browsable_api_renders_form(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("api:users-api:user-list"), HTTP_ACCEPT="text/html")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"<html", response.content)

    def test_group_list_endpoint_returns_groups_for_staff(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("api:users-api:group-list"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["name"], self.group.name)
        self.assertEqual(
            payload["results"][0]["permissions"],
            [
                {
                    "id": self.permission.id,
                    "name": self.permission.name,
                    "codename": self.permission.codename,
                    "content_type": {
                        "id": self.user_content_type.id,
                        "app_label": self.user_content_type.app_label,
                        "model": self.user_content_type.model,
                    },
                }
            ],
        )
        self.assertEqual(
            payload["results"][0]["object_permissions"],
            [
                {
                    "id": self.object_permission.id,
                    "name": self.object_permission.name,
                    "description": self.object_permission.description,
                    "enabled": True,
                    "actions": ["view"],
                }
            ],
        )

    def test_group_create_accepts_primary_keys_for_related_fields(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("api:users-api:group-list"),
            {
                "name": "Engineers",
                "description": "Engineering team",
                "permissions": [self.permission.id],
                "object_permissions": [self.object_permission.id],
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["permissions"][0]["id"], self.permission.id)
        self.assertEqual(payload["object_permissions"][0]["id"], self.object_permission.id)

    def test_membership_list_endpoint_returns_memberships_for_staff(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("api:users-api:membership-list"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["user"]["id"], self.user.id)
        self.assertEqual(payload["results"][0]["organization"]["id"], self.organization.id)
        self.assertEqual(payload["results"][0]["scope_type"], "Organization")
        self.assertEqual(payload["results"][0]["scope_label"], self.organization.name)

    def test_membership_create_accepts_primary_keys_for_scope_and_access(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("api:users-api:membership-list"),
            {
                "user": self.other_user.id,
                "description": "Scoped engineering access",
                "organization": self.organization.id,
                "groups": [self.group.id],
                "object_permissions": [self.object_permission.id],
                "is_active": True,
                "is_default": True,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["user"]["id"], self.other_user.id)
        self.assertEqual(payload["groups"][0]["id"], self.group.id)
        self.assertEqual(payload["object_permissions"][0]["id"], self.object_permission.id)

    def test_group_list_supports_brief_mode(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("api:users-api:group-list"), {"brief": 1})

        self.assertEqual(response.status_code, 200)
        result = response.json()["results"][0]
        self.assertEqual(set(result), {"id", "url", "name", "description"})

    def test_object_permission_list_endpoint_returns_permissions_for_staff(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("api:users-api:objectpermission-list"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["name"], self.object_permission.name)
        self.assertEqual(payload["results"][0]["actions"], ["view"])
        self.assertEqual(
            payload["results"][0]["content_types"],
            [
                {
                    "id": self.user_content_type.id,
                    "app_label": self.user_content_type.app_label,
                    "model": self.user_content_type.model,
                }
            ],
        )
        self.assertEqual(
            payload["results"][0]["groups"],
            [{"id": self.group.id, "name": self.group.name, "description": self.group.description}],
        )
        self.assertEqual(
            payload["results"][0]["users"],
            [
                {
                    "id": self.user.id,
                    "username": self.user.username,
                    "display_name": self.user.display_name,
                    "first_name": self.user.first_name,
                    "last_name": self.user.last_name,
                    "email": self.user.email,
                }
            ],
        )

    def test_object_permission_create_accepts_primary_keys_for_content_types(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("api:users-api:objectpermission-list"),
            {
                "name": "Add users",
                "description": "Add user records",
                "enabled": True,
                "actions": ["add"],
                "content_types": [self.user_content_type.id],
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(
            payload["content_types"],
            [
                {
                    "id": self.user_content_type.id,
                    "app_label": self.user_content_type.app_label,
                    "model": self.user_content_type.model,
                }
            ],
        )

    def test_object_permission_list_browsable_api_renders_form(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("api:users-api:objectpermission-list"), HTTP_ACCEPT="text/html")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"<html", response.content)

    def test_token_list_is_scoped_to_current_user(self):
        Token(user=self.user, description="CLI access").save()
        Token(user=self.other_user, description="Other access").save()
        self.client.force_login(self.user)

        response = self.client.get(reverse("api:users-api:token-list"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["description"], "CLI access")
        self.assertEqual(payload["results"][0]["user"]["id"], self.user.id)
        self.assertEqual(payload["results"][0]["user"]["username"], self.user.username)

    def test_token_authentication_for_token_list(self):
        token = Token(user=self.user, description="CLI access")
        token.save()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.plaintext_token}")

        response = client.get(reverse("api:users-api:token-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["results"][0]["description"], "CLI access")
        self.assertEqual(response.json()["results"][0]["user"]["id"], self.user.id)

        token.refresh_from_db()
        self.assertIsNotNone(token.last_used)

    def test_bearer_authentication_is_not_supported(self):
        token = Token(user=self.user, description="CLI access")
        token.save()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.plaintext_token}")

        response = client.get(reverse("api:users-api:token-list"))

        self.assertEqual(response.status_code, 403)

    def test_token_create_returns_plaintext_token(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("api:users-api:token-list"),
            {
                "description": "Automation access",
                "enabled": True,
                "write_enabled": True,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["description"], "Automation access")
        self.assertTrue(payload["plaintext_token"].startswith("agt_"))
        self.assertEqual(payload["user"]["id"], self.user.id)
        self.assertEqual(payload["user"]["username"], self.user.username)
        self.assertIsNone(payload["scope_membership"])
        self.assertEqual(Token.objects.filter(user=self.user).count(), 1)

    def test_token_create_accepts_membership_scope(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("api:users-api:token-list"),
            {
                "description": "Scoped automation access",
                "enabled": True,
                "write_enabled": True,
                "scope_membership": self.membership.id,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["scope_membership"]["id"], self.membership.id)
        self.assertEqual(payload["scope_membership"]["scope_label"], self.organization.name)

    def test_read_only_token_cannot_create_token(self):
        token = Token(user=self.user, description="Read only", write_enabled=False)
        token.save()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.plaintext_token}")

        response = client.post(
            reverse("api:users-api:token-list"),
            {"description": "Blocked", "enabled": True, "write_enabled": True},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_read_only_staff_token_can_read_but_cannot_write_staff_endpoint(self):
        token = Token(user=self.staff_user, description="Staff read only", write_enabled=False)
        token.save()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.plaintext_token}")

        list_response = client.get(reverse("api:users-api:user-list"))
        create_response = client.post(
            reverse("api:users-api:user-list"),
            {
                "username": "blocked-user",
                "email": "blocked-user@example.com",
                "password": "testpass123",
            },
            format="json",
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(create_response.status_code, 403)

    def test_config_endpoint_returns_current_user_preferences(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("api:users-api:config"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "ui": {
                    "theme": "system",
                    "page_size": 50,
                    "landing_page": "/",
                }
            },
        )

    def test_config_patch_updates_current_user_preferences(self):
        self.client.force_login(self.user)

        response = self.client.patch(
            reverse("api:users-api:config"),
            {
                "ui": {
                    "theme": "dark",
                    "page_size": 100,
                }
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["ui"]["theme"], "dark")
        self.assertEqual(response.json()["ui"]["page_size"], 100)
        self.assertEqual(response.json()["ui"]["landing_page"], "/")

        self.user.refresh_from_db()
        self.assertEqual(self.user.get_config().get("ui.theme"), "dark")
        self.assertEqual(self.user.get_config().get("ui.page_size"), 100)

    def test_read_only_token_cannot_patch_config(self):
        token = Token(user=self.user, description="Read only", write_enabled=False)
        token.save()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.plaintext_token}")

        response = client.patch(
            reverse("api:users-api:config"),
            {"ui": {"theme": "dark"}},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
