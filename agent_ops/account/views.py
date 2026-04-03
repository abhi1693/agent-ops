from django.contrib import messages
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseRedirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import TemplateView

from core.generic_views import ObjectDeleteView, ObjectEditView, ObjectListView
from users import filtersets, tables
from users.models import Token, User
from users.scopes import (
    get_effective_groups,
    get_effective_object_permissions,
    get_request_actor_scope,
    set_active_membership,
)

from .forms import (
    ActiveMembershipForm,
    LoginForm,
    ProfileForm,
    TokenCreateForm,
    UserPreferenceForm,
)


class AgentOpsLoginView(LoginView):
    authentication_form = LoginForm
    template_name = "account/login.html"
    redirect_authenticated_user = True


class AgentOpsLogoutView(LogoutView):
    next_page = reverse_lazy("login")


class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = "account/profile.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        config = user.get_config()
        actor_scope = get_request_actor_scope(self.request)
        membership = actor_scope.membership if actor_scope is not None else None

        context["active_scope"] = actor_scope
        context["active_membership"] = membership
        context["active_membership_form"] = ActiveMembershipForm(
            user=user,
            initial={"membership": membership.pk if membership is not None else None},
        )
        context["tenant_memberships"] = user.get_active_memberships()
        context["managed_permissions"] = get_effective_object_permissions(user, membership)
        context["group_memberships"] = get_effective_groups(user, membership)
        context["preferences"] = config.all()
        return context


class ProfileUpdateView(LoginRequiredMixin, ObjectEditView):
    form_class = ProfileForm
    model = User
    success_message = "Profile updated."
    page_title = "Edit profile"

    def get_object(self, **kwargs):
        return self.request.user

    def get_return_url(self, request, obj=None):
        return reverse("profile")


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
        context["return_url"] = reverse("profile")
        context["is_editing"] = True
        return context


class TokenListView(LoginRequiredMixin, ObjectListView):
    queryset = Token.objects.all()
    table = tables.TokenTable
    filterset = filtersets.TokenFilterSet
    template_name = "account/token_list.html"

    def get_queryset(self, request):
        return request.user.tokens.order_by("-created")


class TokenCreateView(LoginRequiredMixin, ObjectEditView):
    model = Token
    form_class = TokenCreateForm
    page_title = "Create API token"
    submit_label = "Create token"

    def get_form(self, data=None, files=None):
        return self.get_form_class()(
            data=data,
            files=files,
            instance=self.object,
            user=self.request.user,
        )

    def form_save(self, form):
        token = form.save(commit=False)
        token.user = self.request.user
        token.save()
        form.save_m2m()
        return token

    def get_success_message(self, obj, created):
        return f"API token created. Copy it now: {obj.plaintext_token}"

    def get_return_url(self, request, obj=None):
        return reverse("token_list")


class ProfileScopeUpdateView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        form = ActiveMembershipForm(request.POST, user=request.user)
        if form.is_valid():
            membership = form.cleaned_data["membership"]
            set_active_membership(request, membership)
            messages.success(request, "Active tenant scope updated.")
        else:
            messages.error(request, "Unable to update active tenant scope.")
        return HttpResponseRedirect(reverse("profile"))


class TokenDeleteView(LoginRequiredMixin, ObjectDeleteView):
    model = Token
    template_name = "users/token_confirm_delete.html"
    success_message = "API token deleted."

    def get_queryset(self):
        return self.request.user.tokens.all()

    def get_return_url(self, request, obj=None):
        return reverse("token_list")
