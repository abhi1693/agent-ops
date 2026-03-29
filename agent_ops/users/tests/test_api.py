from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from users.models import Group, ObjectPermission, Token, User


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
        cls.object_permission = ObjectPermission.objects.create(
            name="View users",
            description="View user records",
            enabled=True,
            actions=["view"],
        )
        cls.object_permission.content_types.add(ContentType.objects.get_for_model(User))

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

    def test_group_list_endpoint_returns_groups_for_staff(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("api:users-api:group-list"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["name"], self.group.name)

    def test_object_permission_list_endpoint_returns_permissions_for_staff(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("api:users-api:objectpermission-list"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["name"], self.object_permission.name)
        self.assertEqual(payload["results"][0]["actions"], ["view"])

    def test_token_list_is_scoped_to_current_user(self):
        Token(user=self.user, description="CLI access").save()
        Token(user=self.other_user, description="Other access").save()
        self.client.force_login(self.user)

        response = self.client.get(reverse("api:users-api:token-list"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["description"], "CLI access")

    def test_token_authentication_for_token_list(self):
        token = Token(user=self.user, description="CLI access")
        token.save()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.plaintext_token}")

        response = client.get(reverse("api:users-api:token-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["results"][0]["description"], "CLI access")

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
        self.assertEqual(Token.objects.filter(user=self.user).count(), 1)

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
