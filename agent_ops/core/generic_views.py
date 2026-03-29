from django.core.exceptions import ImproperlyConfigured
from django.shortcuts import render
from django.views.generic import View

from core.form_widgets import apply_standard_widget_classes


__all__ = (
    "BaseMultiObjectView",
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
