from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import (
    GroupForm,
    ObjectPermissionForm,
    UserCreateForm,
    UserUpdateForm,
)
from .mixins import StaffRequiredMixin
from .models import Group, ObjectPermission, User


class UserListView(StaffRequiredMixin, ListView):
    model = User
    template_name = "users/user_list.html"
    context_object_name = "users"

    def get_queryset(self):
        return User.objects.order_by("username")


class UserDetailView(StaffRequiredMixin, DetailView):
    model = User
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


class GroupListView(StaffRequiredMixin, ListView):
    model = Group
    template_name = "users/group_list.html"
    context_object_name = "groups"

    def get_queryset(self):
        return Group.objects.order_by("name")


class GroupDetailView(StaffRequiredMixin, DetailView):
    model = Group
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


class ObjectPermissionListView(StaffRequiredMixin, ListView):
    model = ObjectPermission
    template_name = "users/objectpermission_list.html"
    context_object_name = "object_permissions"

    def get_queryset(self):
        return ObjectPermission.objects.order_by("name")


class ObjectPermissionDetailView(StaffRequiredMixin, DetailView):
    model = ObjectPermission
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
