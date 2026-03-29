import django_tables2 as tables
from django.core.exceptions import FieldDoesNotExist
from django.db.models.fields.related import RelatedField
from django.db.models.fields.reverse_related import ManyToOneRel
from django.utils.translation import gettext_lazy as _
from django_tables2.data import TableQuerysetData

from core.paginator import EnhancedPaginator, get_paginate_count


__all__ = (
    "AgentOpsTable",
    "BaseTable",
)


class BaseTable(tables.Table):
    exempt_columns = ()

    class Meta:
        attrs = {
            "class": "table table-hover object-list",
        }
        template_name = "inc/table.html"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.empty_text is None and getattr(self._meta, "model", None) is not None:
            model = self._meta.model._meta.verbose_name_plural
            self.empty_text = _("No %(model_name)s found") % {"model_name": model}

    @property
    def name(self):
        return self.__class__.__name__

    def _get_columns(self, visible=True):
        columns = []
        for name, column in self.columns.items():
            if column.visible == visible and name not in self.exempt_columns:
                columns.append((name, column.verbose_name))
        return columns

    @property
    def available_columns(self):
        return sorted(self._get_columns(visible=False))

    @property
    def selected_columns(self):
        return self._get_columns(visible=True)

    def _set_columns(self, selected_columns):
        if not selected_columns:
            return

        selected_column_names = list(selected_columns)

        for column in self.columns:
            if column.name not in [*selected_column_names, *self.exempt_columns]:
                self.columns.hide(column.name)

        self.sequence = [
            *[name for name in selected_column_names if name in self.columns.names()],
            *[name for name in self.columns.names() if name not in selected_column_names],
        ]

    def _apply_prefetching(self):
        if not isinstance(self.data, TableQuerysetData):
            return

        model = getattr(self.Meta, "model", None)
        if model is None:
            return

        prefetch_fields = []

        for column in self.columns:
            if not column.visible:
                continue

            accessor = getattr(column, "accessor", None)
            if not accessor:
                continue

            accessor = str(accessor)
            if accessor == "None":
                continue

            current_model = model
            prefetch_path = []

            for field_name in accessor.split("__"):
                try:
                    field = current_model._meta.get_field(field_name)
                except FieldDoesNotExist:
                    break

                if isinstance(field, (RelatedField, ManyToOneRel)):
                    prefetch_path.append(field_name)
                    current_model = field.remote_field.model
                    continue

                break

            if prefetch_path:
                prefetch_fields.append("__".join(prefetch_path))

        if prefetch_fields:
            self.data.data = self.data.data.prefetch_related(*sorted(set(prefetch_fields)))

    def configure(self, request):
        columns = None
        ordering = None

        if self.prefixed_order_by_field in request.GET:
            requested_ordering = request.GET.getlist(self.prefixed_order_by_field)
            if requested_ordering and any(value for value in requested_ordering):
                ordering = requested_ordering
                user = getattr(request, "user", None)
                if user is not None and user.is_authenticated and hasattr(user, "get_config"):
                    user.get_config().set(f"tables.{self.name}.ordering", ordering, commit=True)
            else:
                user = getattr(request, "user", None)
                if user is not None and user.is_authenticated and hasattr(user, "get_config"):
                    user.get_config().clear(f"tables.{self.name}.ordering", commit=True)

        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and hasattr(user, "get_config"):
            user_config = user.get_config()
            if columns is None:
                columns = user_config.get(f"tables.{self.name}.columns")
            if ordering is None:
                ordering = user_config.get(f"tables.{self.name}.ordering")

        if columns is None:
            columns = getattr(self.Meta, "default_columns", getattr(self.Meta, "fields", ()))

        self._set_columns(columns)
        self._apply_prefetching()

        if ordering:
            self.order_by = ordering

        paginate = {
            "paginator_class": EnhancedPaginator,
            "per_page": get_paginate_count(request),
        }
        tables.RequestConfig(request, paginate).configure(self)


class AgentOpsTable(BaseTable):
    class Meta(BaseTable.Meta):
        pass
