from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Count
from django.urls import reverse
from django.views.generic import CreateView, UpdateView

from core.generic_views import ObjectListView, ObjectView
from . import filtersets, tables
from .forms import (
    GroupForm,
    ObjectPermissionForm,
    UserCreateForm,
    UserUpdateForm,
)
from .mixins import StaffRequiredMixin
from .models import Group, ObjectPermission, User


class UserListView(StaffRequiredMixin, ObjectListView):
    queryset = User.objects.all()
    table = tables.UserTable
    filterset = filtersets.UserFilterSet
    template_name = "users/user_list.html"

    def get_queryset(self, request):
        return super().get_queryset(request).order_by("username")


class UserDetailView(StaffRequiredMixin, ObjectView):
    model = User
    queryset = User.objects.prefetch_related("groups", "object_permissions", "user_permissions").annotate(
        group_count=Count("groups", distinct=True),
        object_permission_count=Count("object_permissions", distinct=True),
        user_permission_count=Count("user_permissions", distinct=True),
        token_count=Count("tokens", distinct=True),
    )
    template_name = "users/user_detail.html"


class UserCreateView(StaffRequiredMixin, SuccessMessageMixin, CreateView):
    model = User
    form_class = UserCreateForm
    template_name = "users/model_form.html"
    success_message = "User created."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Create user"
        context["submit_label"] = "Create user"
        context["cancel_url"] = reverse("user_list")
        return context


class UserUpdateView(StaffRequiredMixin, SuccessMessageMixin, UpdateView):
    model = User
    form_class = UserUpdateForm
    template_name = "users/model_form.html"
    success_message = "User updated."

    def get_success_url(self):
        return self.object.get_absolute_url()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"Edit user: {self.object.username}"
        context["submit_label"] = "Save user"
        context["cancel_url"] = self.object.get_absolute_url()
        return context


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


class GroupCreateView(StaffRequiredMixin, SuccessMessageMixin, CreateView):
    model = Group
    form_class = GroupForm
    template_name = "users/model_form.html"
    success_message = "Group created."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Create group"
        context["submit_label"] = "Create group"
        context["cancel_url"] = reverse("group_list")
        return context


class GroupUpdateView(StaffRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Group
    form_class = GroupForm
    template_name = "users/model_form.html"
    success_message = "Group updated."

    def get_success_url(self):
        return self.object.get_absolute_url()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"Edit group: {self.object.name}"
        context["submit_label"] = "Save group"
        context["cancel_url"] = self.object.get_absolute_url()
        return context


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


class ObjectPermissionCreateView(StaffRequiredMixin, SuccessMessageMixin, CreateView):
    model = ObjectPermission
    form_class = ObjectPermissionForm
    template_name = "users/model_form.html"
    success_message = "Object permission created."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Create object permission"
        context["submit_label"] = "Create permission"
        context["cancel_url"] = reverse("objectpermission_list")
        return context


class ObjectPermissionUpdateView(StaffRequiredMixin, SuccessMessageMixin, UpdateView):
    model = ObjectPermission
    form_class = ObjectPermissionForm
    template_name = "users/model_form.html"
    success_message = "Object permission updated."

    def get_success_url(self):
        return self.object.get_absolute_url()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"Edit object permission: {self.object.name}"
        context["submit_label"] = "Save permission"
        context["cancel_url"] = self.object.get_absolute_url()
        return context
