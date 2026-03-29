from django.contrib import messages
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Count, Q
from django.http import HttpResponseRedirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from .forms import (
    GroupForm,
    LoginForm,
    ObjectPermissionForm,
    ProfileForm,
    TokenCreateForm,
    UserCreateForm,
    UserPreferenceForm,
    UserUpdateForm,
)
from .models import Group, ObjectPermission, Token, User


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    raise_exception = True

    def test_func(self):
        user = self.request.user
        return user.is_staff or user.is_superuser


class AgentOpsLoginView(LoginView):
    authentication_form = LoginForm
    template_name = "users/login.html"
    redirect_authenticated_user = True


class AgentOpsLogoutView(LogoutView):
    next_page = reverse_lazy("login")


class HomeView(LoginRequiredMixin, TemplateView):
    template_name = "users/home.html"
    login_url = reverse_lazy("login")

    @staticmethod
    def _stat_item(label, count, url, disabled=False):
        return {
            "label": label,
            "count": count,
            "url": url,
            "disabled": disabled,
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        config = user.get_config()
        is_staff = user.is_staff or user.is_superuser
        now = timezone.now()

        user_tokens = user.tokens.all()
        active_tokens = user_tokens.filter(enabled=True).filter(Q(expires__isnull=True) | Q(expires__gt=now))
        writable_tokens = active_tokens.filter(write_enabled=True)
        direct_permissions = user.object_permissions.order_by("name")
        group_memberships = user.groups.order_by("name")

        user_count = User.objects.count()
        group_count = Group.objects.count()
        object_permission_count = ObjectPermission.objects.count()

        context["stats"] = [
            (
                "Your Account",
                [
                    self._stat_item("Preferences", len(config.all()), "preferences"),
                    self._stat_item("Group Memberships", group_memberships.count(), "profile"),
                    self._stat_item("Direct Permissions", direct_permissions.count(), "profile"),
                ],
                "account-circle-outline",
            ),
            (
                "Automation",
                [
                    self._stat_item("All Tokens", user_tokens.count(), "token_list"),
                    self._stat_item("Active Tokens", active_tokens.count(), "token_list"),
                    self._stat_item("Writable Tokens", writable_tokens.count(), "token_list"),
                ],
                "key-chain-variant",
            ),
            (
                "Administration",
                [
                    self._stat_item("Users", user_count, "user_list", disabled=not is_staff),
                    self._stat_item("Groups", group_count, "group_list", disabled=not is_staff),
                    self._stat_item(
                        "Object Permissions",
                        object_permission_count,
                        "objectpermission_list",
                        disabled=not is_staff,
                    ),
                ],
                "shield-account-outline",
            ),
        ]

        context["recent_tokens"] = user_tokens.order_by("-created")[:5]
        context["group_memberships"] = group_memberships[:5]
        context["direct_permissions"] = direct_permissions[:5]
        context["is_staff_dashboard"] = is_staff

        if is_staff:
            context["newest_users"] = User.objects.order_by("-date_joined")[:5]
            context["catalog_groups"] = Group.objects.annotate(member_total=Count("user")).order_by("name")[:5]
            context["catalog_permissions"] = ObjectPermission.objects.order_by("name")[:5]
        return context


class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = "users/profile.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        config = user.get_config()
        context["managed_permissions"] = user.object_permissions.order_by("name")
        context["group_memberships"] = user.groups.order_by("name")
        context["preferences"] = config.all()
        return context


class ProfileUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    form_class = ProfileForm
    model = User
    template_name = "users/model_form.html"
    success_message = "Profile updated."

    def get_object(self, queryset=None):
        return self.request.user

    def get_success_url(self):
        return reverse("profile")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edit profile"
        context["submit_label"] = "Save profile"
        context["cancel_url"] = reverse("profile")
        return context


class PreferenceUpdateView(LoginRequiredMixin, TemplateView):
    template_name = "users/model_form.html"

    def get(self, request, *args, **kwargs):
        form = UserPreferenceForm(config=request.user.get_config())
        return self.render_to_response(self.get_context_data(form=form))

    def post(self, request, *args, **kwargs):
        form = UserPreferenceForm(request.POST, config=request.user.get_config())
        if form.is_valid():
            form.save()
            messages.success(request, "Preferences updated.")
            return HttpResponseRedirect(reverse("profile"))
        return self.render_to_response(self.get_context_data(form=form))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Preferences"
        context["submit_label"] = "Save preferences"
        context["cancel_url"] = reverse("profile")
        return context


class TokenListView(LoginRequiredMixin, ListView):
    template_name = "users/token_list.html"
    context_object_name = "tokens"

    def get_queryset(self):
        return self.request.user.tokens.order_by("-created")


class TokenCreateView(LoginRequiredMixin, CreateView):
    model = Token
    form_class = TokenCreateForm
    template_name = "users/model_form.html"

    def form_valid(self, form):
        token = form.save(commit=False)
        token.user = self.request.user
        token.save()
        messages.success(
            self.request,
            f"API token created. Copy it now: {token.plaintext_token}",
        )
        return HttpResponseRedirect(reverse("token_list"))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Create API token"
        context["submit_label"] = "Create token"
        context["cancel_url"] = reverse("token_list")
        return context


class TokenDeleteView(LoginRequiredMixin, DeleteView):
    template_name = "users/token_confirm_delete.html"

    def get_queryset(self):
        return self.request.user.tokens.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cancel_url"] = reverse("token_list")
        return context

    def get_success_url(self):
        messages.success(self.request, "API token deleted.")
        return reverse("token_list")


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

    def get_success_url(self):
        return self.object.get_absolute_url()

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

    def get_success_url(self):
        return self.object.get_absolute_url()

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

    def get_success_url(self):
        return self.object.get_absolute_url()

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
