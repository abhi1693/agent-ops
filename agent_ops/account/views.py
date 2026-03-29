from django.contrib import messages
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.http import HttpResponseRedirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, TemplateView, UpdateView

from core.generic_views import ObjectListView
from users import filtersets, tables
from users.models import Token, User

from .forms import LoginForm, ProfileForm, TokenCreateForm, UserPreferenceForm


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


class TokenListView(LoginRequiredMixin, ObjectListView):
    queryset = Token.objects.all()
    table = tables.TokenTable
    filterset = filtersets.TokenFilterSet
    template_name = "account/token_list.html"

    def get_queryset(self, request):
        return request.user.tokens.order_by("-created")


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
