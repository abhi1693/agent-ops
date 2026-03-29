from urllib.parse import quote

import django_tables2 as tables
from django.core.exceptions import FieldDoesNotExist
from django.db.models.fields.related import RelatedField
from django.db.models.fields.reverse_related import ManyToOneRel
from django.urls import NoReverseMatch, reverse
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django_tables2.data import TableQuerysetData

from core.paginator import EnhancedPaginator, get_paginate_count


__all__ = (
    "AgentOpsTable",
    "BaseTable",
    "RowActionsColumn",
)


class RowActionsColumn(tables.Column):
    attrs = {
        "td": {
            "class": "text-end text-nowrap noprint p-1",
        }
    }
    empty_values = ()
    action_map = {
        "edit": {
            "label": "Edit",
            "icon": "pencil",
            "btn_class": "warning",
        },
        "delete": {
            "label": "Delete",
            "icon": "trash-can-outline",
            "btn_class": "danger",
        },
    }

    def __init__(self, *args, actions=("edit", "delete"), split_actions=True, **kwargs):
        kwargs.setdefault("verbose_name", "")
        kwargs.setdefault("orderable", False)
        super().__init__(*args, **kwargs)
        self.actions = actions
        self.split_actions = split_actions

    def header(self):
        return ""

    def _get_action_url(self, record, action, request):
        try:
            url = reverse(f"{record._meta.model_name}_{action}", args=[record.pk])
        except NoReverseMatch:
            return None

        if request is not None:
            return_url = quote(request.get_full_path())
            return f"{url}?return_url={return_url}"

        return url

    def render(self, record, table, **kwargs):
        request = getattr(table, "request", None)
        actions = []

        for action_name in self.actions:
            action = self.action_map.get(action_name)
            if action is None:
                continue

            url = self._get_action_url(record, action_name, request)
            if url is None:
                continue

            actions.append(
                {
                    "label": action["label"],
                    "icon": action["icon"],
                    "btn_class": action["btn_class"],
                    "url": url,
                }
            )

        if not actions:
            return ""

        direct_action = actions[0] if len(actions) == 1 or self.split_actions else None
        dropdown_actions = actions[1:] if direct_action else actions
        html = []

        if direct_action and dropdown_actions:
            html.append('<span class="btn-group dropdown">')
        elif dropdown_actions:
            html.append('<span class="btn-group dropdown">')

        if direct_action:
            html.append(
                (
                    f'<a class="btn btn-sm btn-{direct_action["btn_class"]}" '
                    f'href="{direct_action["url"]}" aria-label="{direct_action["label"]}">'
                    f'<i class="mdi mdi-{direct_action["icon"]}" aria-hidden="true"></i>'
                    '</a>'
                )
            )

        if dropdown_actions:
            toggle_class = direct_action["btn_class"] if direct_action else "secondary"
            toggle_style = ' style="padding-left: 2px"' if direct_action else ""
            html.append(
                (
                    f'<a class="btn btn-sm btn-{toggle_class} dropdown-toggle" '
                    f'type="button" data-bs-toggle="dropdown"{toggle_style}>'
                    f'<span class="visually-hidden">{_("Toggle Dropdown")}</span>'
                    '</a>'
                    '<ul class="dropdown-menu">'
                )
            )

            for action in dropdown_actions:
                html.append(
                    (
                        "<li>"
                        f'<a class="dropdown-item" href="{action["url"]}">'
                        f'<i class="mdi mdi-{action["icon"]}" aria-hidden="true"></i> {action["label"]}'
                        "</a>"
                        "</li>"
                    )
                )

            html.append("</ul>")

        if direct_action or dropdown_actions:
            if direct_action and dropdown_actions:
                html.append("</span>")
            elif dropdown_actions:
                html.append("</span>")

        return mark_safe("".join(html))


class BaseTable(tables.Table):
    exempt_columns = ()

    class Meta:
        attrs = {
            "class": "table table-hover object-list",
        }
        template_name = "inc/table.html"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._configure_structural_columns()

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

    def _append_column_class(self, column_name, target, css_class):
        if column_name not in self.columns.names():
            return

        column = self.columns[column_name].column
        attrs = column.attrs.setdefault(target, {})
        existing = attrs.get("class", "")
        classes = existing.split()

        if css_class not in classes:
            classes.append(css_class)

        attrs["class"] = " ".join(classes).strip()

    def _configure_structural_columns(self):
        if "pk" in self.columns.names():
            self._append_column_class("pk", "th", "column-select")
            self._append_column_class("pk", "td", "column-select")

        if "actions" in self.columns.names():
            self._append_column_class("actions", "th", "column-actions")
            self._append_column_class("actions", "td", "column-actions")
            self._append_column_class("actions", "td", "text-nowrap")

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

        if "pk" in self.sequence:
            self.sequence.remove("pk")
            self.sequence.insert(0, "pk")

        if "actions" in self.sequence:
            self.sequence.remove("actions")
            self.sequence.append("actions")

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
