from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import TemplateView

from core.changelog import restrict_objectchange_queryset
from core.generic_views import ObjectListView
from core.models import ObjectChange

from . import filtersets, tables
from .dashboard import build_dashboard_context


class HomeView(LoginRequiredMixin, TemplateView):
    template_name = "core/home.html"
    login_url = reverse_lazy("login")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(build_dashboard_context(self.request))
        return context


class ObjectChangeListView(LoginRequiredMixin, ObjectListView):
    queryset = ObjectChange.objects.select_related(
        "user",
        "changed_object_type",
        "related_object_type",
    )
    table = tables.ObjectChangeTable
    filterset = filtersets.ObjectChangeFilterSet
    template_name = "core/objectchange_list.html"
    login_url = reverse_lazy("login")

    def get_queryset(self, request):
        queryset = super().get_queryset(request).order_by("-time")
        return restrict_objectchange_queryset(queryset, request=request)
