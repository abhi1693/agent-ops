from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from users.models import Group, ObjectPermission, User


class ListViewTests(TestCase):
    def setUp(self) -> None:
        self.staff_user = User.objects.create_user(
            username="operator",
            email="operator@example.com",
            password="correct-horse-battery-staple",
            is_staff=True,
        )
        self.user_alpha = User.objects.create_user(
            username="alpha",
            email="alpha@example.com",
            password="correct-horse-battery-staple",
            display_name="Alpha User",
            is_active=True,
        )
        self.user_beta = User.objects.create_user(
            username="beta",
            email="beta@example.com",
            password="correct-horse-battery-staple",
            display_name="Beta User",
            is_active=False,
        )

        self.group = Group.objects.create(name="Operators", description="Operations team")
        self.group.users.add(self.staff_user, self.user_alpha)
        self.group.permissions.add(Permission.objects.order_by("pk").first())

        self.user_content_type = ContentType.objects.get_for_model(User)
        self.permission_view = ObjectPermission.objects.create(
            name="View users",
            enabled=True,
            actions=["view"],
        )
        self.permission_view.content_types.add(self.user_content_type)

        self.permission_delete = ObjectPermission.objects.create(
            name="Delete users",
            enabled=False,
            actions=["delete"],
        )
        self.permission_delete.content_types.add(self.user_content_type)

        self.group.object_permissions.add(self.permission_view)
        self.client.force_login(self.staff_user)

    def test_user_list_uses_shared_table_without_filter_ui(self) -> None:
        response = self.client.get(reverse("user_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Results")
        self.assertNotContains(response, "Quick search")
        self.assertNotContains(response, "Per page")
        self.assertNotContains(response, "Filters")
        self.assertContains(response, "Alpha User")
        self.assertContains(response, "Beta User")
        self.assertContains(response, reverse("user_edit", args=[self.user_alpha.pk]))
        self.assertContains(response, reverse("user_delete", args=[self.user_alpha.pk]))
        self.assertNotContains(response, "dropdown-toggle")
        self.assertEqual(response.context["table"].paginator.count, 3)

    def test_user_list_supports_query_param_filtering(self) -> None:
        response = self.client.get(reverse("user_list"), {"q": "beta"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "beta@example.com")
        self.assertNotContains(response, "alpha@example.com")
        self.assertEqual(response.context["table"].paginator.count, 1)

    def test_group_list_annotates_member_and_permission_counts(self) -> None:
        response = self.client.get(reverse("group_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("group_edit", args=[self.group.pk]))
        self.assertContains(response, reverse("group_delete", args=[self.group.pk]))
        group = next(
            group
            for group in response.context["table"].data.data
            if group.pk == self.group.pk
        )
        self.assertEqual(group.user_count, 2)
        self.assertEqual(group.permission_count, 1)
        self.assertEqual(group.object_permission_count, 1)

    def test_object_permission_list_filters_by_action_and_enabled(self) -> None:
        response = self.client.get(
            reverse("objectpermission_list"),
            {"action": "view", "enabled": "true"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "View users")
        self.assertNotContains(response, "Delete users")
        self.assertContains(response, reverse("objectpermission_edit", args=[self.permission_view.pk]))
        self.assertContains(response, reverse("objectpermission_delete", args=[self.permission_view.pk]))
        self.assertEqual(response.context["table"].paginator.count, 1)
