from django.db.models import Count

from core.generic_views import ObjectDeleteView, ObjectEditView, ObjectListView, ObjectView
from . import filtersets, tables
from .forms import (
    GroupForm,
    MembershipForm,
    ObjectPermissionForm,
    UserCreateForm,
    UserUpdateForm,
)
from .mixins import StaffRequiredMixin
from .models import Group, Membership, ObjectPermission, User


class UserListView(StaffRequiredMixin, ObjectListView):
    queryset = User.objects.all()
    table = tables.UserTable
    filterset = filtersets.UserFilterSet
    template_name = "users/user_list.html"

    def get_queryset(self, request):
        return super().get_queryset(request).order_by("username")


class UserDetailView(StaffRequiredMixin, ObjectView):
    model = User
    queryset = User.objects.prefetch_related(
        "groups",
        "object_permissions",
        "user_permissions",
        "memberships__organization",
        "memberships__workspace",
        "memberships__environment",
    ).annotate(
        group_count=Count("groups", distinct=True),
        membership_count=Count("memberships", distinct=True),
        object_permission_count=Count("object_permissions", distinct=True),
        user_permission_count=Count("user_permissions", distinct=True),
        token_count=Count("tokens", distinct=True),
    )
    template_name = "users/user_detail.html"


class UserCreateView(StaffRequiredMixin, ObjectEditView):
    model = User
    form_class = UserCreateForm
    success_message = "User created."


class UserUpdateView(StaffRequiredMixin, ObjectEditView):
    model = User
    form_class = UserUpdateForm
    success_message = "User updated."


class UserDeleteView(StaffRequiredMixin, ObjectDeleteView):
    model = User
    success_message = "User deleted."


class GroupListView(StaffRequiredMixin, ObjectListView):
    queryset = Group.objects.all()
    table = tables.GroupTable
    filterset = filtersets.GroupFilterSet
    template_name = "users/group_list.html"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                user_count=Count("user", distinct=True),
                permission_count=Count("permissions", distinct=True),
                object_permission_count=Count("object_permissions", distinct=True),
            )
            .order_by("name")
        )


class GroupDetailView(StaffRequiredMixin, ObjectView):
    model = Group
    queryset = Group.objects.prefetch_related("users", "permissions", "object_permissions").annotate(
        member_count=Count("user", distinct=True),
        permission_count=Count("permissions", distinct=True),
        object_permission_count=Count("object_permissions", distinct=True),
    )
    template_name = "users/group_detail.html"


class GroupCreateView(StaffRequiredMixin, ObjectEditView):
    model = Group
    form_class = GroupForm
    success_message = "Group created."


class GroupUpdateView(StaffRequiredMixin, ObjectEditView):
    model = Group
    form_class = GroupForm
    success_message = "Group updated."


class GroupDeleteView(StaffRequiredMixin, ObjectDeleteView):
    model = Group
    success_message = "Group deleted."


class ObjectPermissionListView(StaffRequiredMixin, ObjectListView):
    queryset = ObjectPermission.objects.all()
    table = tables.ObjectPermissionTable
    filterset = filtersets.ObjectPermissionFilterSet
    template_name = "users/objectpermission_list.html"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(content_type_count=Count("content_types", distinct=True))
            .order_by("name")
        )


class ObjectPermissionDetailView(StaffRequiredMixin, ObjectView):
    model = ObjectPermission
    queryset = ObjectPermission.objects.prefetch_related("content_types", "users", "groups").annotate(
        content_type_count=Count("content_types", distinct=True),
        user_count=Count("users", distinct=True),
        group_count=Count("groups", distinct=True),
    )
    template_name = "users/objectpermission_detail.html"


class ObjectPermissionCreateView(StaffRequiredMixin, ObjectEditView):
    model = ObjectPermission
    form_class = ObjectPermissionForm
    success_message = "Object permission created."


class ObjectPermissionUpdateView(StaffRequiredMixin, ObjectEditView):
    model = ObjectPermission
    form_class = ObjectPermissionForm
    success_message = "Object permission updated."


class ObjectPermissionDeleteView(StaffRequiredMixin, ObjectDeleteView):
    model = ObjectPermission
    success_message = "Object permission deleted."


class MembershipListView(StaffRequiredMixin, ObjectListView):
    queryset = Membership.objects.all()
    table = tables.MembershipTable
    filterset = filtersets.MembershipFilterSet
    template_name = "users/membership_list.html"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("user", "organization", "workspace", "environment")
            .annotate(
                group_count=Count("groups", distinct=True),
                object_permission_count=Count("object_permissions", distinct=True),
            )
            .order_by(
                "user__username",
                "organization__name",
                "workspace__name",
                "environment__name",
            )
        )


class MembershipDetailView(StaffRequiredMixin, ObjectView):
    model = Membership
    queryset = Membership.objects.select_related(
        "user",
        "organization",
        "workspace",
        "environment",
    ).prefetch_related("groups", "object_permissions").annotate(
        group_count=Count("groups", distinct=True),
        object_permission_count=Count("object_permissions", distinct=True),
    )
    template_name = "users/membership_detail.html"


class MembershipCreateView(StaffRequiredMixin, ObjectEditView):
    model = Membership
    form_class = MembershipForm
    success_message = "Membership created."


class MembershipUpdateView(StaffRequiredMixin, ObjectEditView):
    model = Membership
    form_class = MembershipForm
    success_message = "Membership updated."


class MembershipDeleteView(StaffRequiredMixin, ObjectDeleteView):
    model = Membership
    success_message = "Membership deleted."
