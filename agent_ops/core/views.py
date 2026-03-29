from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import TemplateView

from .dashboard import build_dashboard_context


class HomeView(LoginRequiredMixin, TemplateView):
    template_name = "core/home.html"
    login_url = reverse_lazy("login")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(build_dashboard_context(self.request))
        return context

