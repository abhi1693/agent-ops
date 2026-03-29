from django.test import TestCase
from django.urls import reverse
from django.conf import settings
from rest_framework.test import APIClient

from users.models import Group, Token, User


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
        cls.group = Group.objects.create(name="Operators", description="Operations team")

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

    def test_token_authentication_for_user_list(self):
        token = Token(user=self.user, description="CLI access")
        token.save()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.plaintext_token}")

        response = client.get(reverse("api:users-api:user-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["results"][0]["username"], self.user.username)

        token.refresh_from_db()
        self.assertIsNotNone(token.last_used)

    def test_bearer_authentication_is_not_supported(self):
        token = Token(user=self.user, description="CLI access")
        token.save()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.plaintext_token}")

        response = client.get(reverse("api:users-api:user-list"))

        self.assertEqual(response.status_code, 403)

    def test_users_api_root_lists_registered_endpoints(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("api:users-api:api-root"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "groups": "http://testserver/api/users/groups/",
                "users": "http://testserver/api/users/users/",
            },
        )

    def test_user_list_endpoint_returns_paginated_results(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("api:users-api:user-list"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["username"], self.user.username)

    def test_group_list_endpoint_returns_groups(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("api:users-api:group-list"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["name"], self.group.name)
