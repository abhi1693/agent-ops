from django.contrib.auth.views import LoginView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import TemplateView

from .forms import LoginForm


class AgentOpsLoginView(LoginView):
    authentication_form = LoginForm
    template_name = "users/login.html"
    redirect_authenticated_user = True


class HomeView(LoginRequiredMixin, TemplateView):
    template_name = "users/home.html"
    login_url = reverse_lazy("login")
