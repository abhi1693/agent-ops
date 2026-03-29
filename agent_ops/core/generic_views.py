from django.core.exceptions import ImproperlyConfigured
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.views.generic import DetailView, View

from core.form_widgets import apply_standard_widget_classes


__all__ = (
    "BaseMultiObjectView",
    "ObjectView",
    "ObjectListView",
    "TableMixin",
)


class BaseMultiObjectView(View):
    queryset = None
    table = None
    template_name = None

    def dispatch(self, request, *args, **kwargs):
        self.queryset = self.get_queryset(request)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self, request):
        if self.queryset is None:
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} does not define a queryset. "
                "Set queryset on the class or override get_queryset()."
            )

        return self.queryset.all()

    def get_extra_context(self, request):
        return {}


class TableMixin:
    def get_table(self, data, request):
        if self.table is None:
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} does not define a table class."
            )

        table = self.table(data)
        table.configure(request)
        return table


class ObjectView(DetailView):
    def get_list_url(self):
        try:
            return reverse(f"{self.object._meta.model_name}_list")
        except NoReverseMatch:
            return None

    def get_object_identifier(self):
        return f"{self.object._meta.app_label}.{self.object._meta.model_name}:{self.object.pk}"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        meta = self.object._meta

        context.update(
            {
                "object_identifier": self.get_object_identifier(),
                "object_list_url": self.get_list_url(),
                "object_verbose_name": str(meta.verbose_name).title(),
                "object_verbose_name_plural": str(meta.verbose_name_plural).title(),
            }
        )
        return context


class ObjectListView(BaseMultiObjectView, TableMixin):
    template_name = "generic/object_list.html"
    filterset = None

    def get(self, request, *args, **kwargs):
        filterset = None
        queryset = self.queryset

        if self.filterset is not None:
            filterset = self.filterset(request.GET, queryset=queryset, request=request)
            queryset = filterset.qs
            apply_standard_widget_classes(filterset.form)

        table = self.get_table(queryset, request)

        context = {
            "model": queryset.model,
            "table": table,
            "filterset": filterset,
            "filter_form": filterset.form if filterset is not None else None,
            **self.get_extra_context(request),
        }

        return render(request, self.template_name, context)
