from django.contrib import messages
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseRedirect
from django.urls import reverse, reverse_lazy
from django.views.generic import TemplateView

from core.generic_views import ObjectDeleteView, ObjectEditView, ObjectListView
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
        context["show_add_another"] = False
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
    show_add_another = False

    def form_save(self, form):
        token = form.save(commit=False)
        token.user = self.request.user
        token.save()
        return token

    def get_success_message(self, obj, created):
        return f"API token created. Copy it now: {obj.plaintext_token}"

    def get_return_url(self, request, obj=None):
        return reverse("token_list")


class TokenDeleteView(LoginRequiredMixin, ObjectDeleteView):
    model = Token
    template_name = "users/token_confirm_delete.html"
    success_message = "API token deleted."

    def get_queryset(self):
        return self.request.user.tokens.all()

    def get_return_url(self, request, obj=None):
        return reverse("token_list")
