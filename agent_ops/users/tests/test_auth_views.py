from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AuthViewTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="alice",
            email="alice@example.com",
            password="correct-horse-battery-staple",
        )

    def test_home_redirects_anonymous_user_to_login(self) -> None:
        response = self.client.get(reverse("home"))

        self.assertRedirects(response, f"{reverse('login')}?next={reverse('home')}")

    def test_login_page_renders(self) -> None:
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sign in")

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

    def test_home_renders_for_authenticated_user(self) -> None:
        self.client.force_login(self.user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Welcome, alice")
        self.assertContains(response, "alice@example.com")

    def test_logout_clears_session(self) -> None:
        self.client.force_login(self.user)

        response = self.client.post(reverse("logout"))

        self.assertRedirects(response, reverse("login"))
        self.assertNotIn("_auth_user_id", self.client.session)
