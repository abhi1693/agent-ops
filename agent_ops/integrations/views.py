from django.core.exceptions import ValidationError

from core.generic_views import (
    ObjectChangeLogView,
    ObjectDeleteView,
    ObjectEditView,
    ObjectListView,
    ObjectView,
)
from integrations import filtersets, tables
from integrations.forms import SecretForm
from integrations.models import Secret
from tenancy.mixins import (
    RestrictedObjectChangeLogMixin,
    RestrictedObjectDeleteMixin,
    RestrictedObjectEditMixin,
    RestrictedObjectListMixin,
    RestrictedObjectViewMixin,
)


class SecretListView(RestrictedObjectListMixin, ObjectListView):
    queryset = Secret.objects.select_related("organization", "workspace", "environment")
    table = tables.SecretTable
    filterset = filtersets.SecretFilterSet
    template_name = "integrations/secret_list.html"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("organization", "workspace", "environment")
            .order_by("organization__name", "workspace__name", "environment__name", "name")
        )


class SecretDetailView(RestrictedObjectViewMixin, ObjectView):
    model = Secret
    template_name = "integrations/secret_detail.html"

    def get_queryset(self):
        return super().get_queryset().select_related("organization", "workspace", "environment")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            context["secret_value"] = self.object.get_value()
            context["secret_value_error"] = ""
        except ValidationError as exc:
            if hasattr(exc, "message_dict"):
                error_message = " ".join(
                    " ".join(messages)
                    for messages in exc.message_dict.values()
                )
            else:
                error_message = " ".join(exc.messages)
            context["secret_value"] = ""
            context["secret_value_error"] = error_message

        return context


class SecretChangelogView(RestrictedObjectChangeLogMixin, ObjectChangeLogView):
    model = Secret
    queryset = Secret.objects.select_related("organization", "workspace", "environment").order_by(
        "organization__name",
        "workspace__name",
        "environment__name",
        "name",
    )


class SecretCreateView(RestrictedObjectEditMixin, ObjectEditView):
    model = Secret
    form_class = SecretForm
    success_message = "Secret created."


class SecretUpdateView(RestrictedObjectEditMixin, ObjectEditView):
    model = Secret
    form_class = SecretForm
    success_message = "Secret updated."


class SecretDeleteView(RestrictedObjectDeleteMixin, ObjectDeleteView):
    model = Secret
    success_message = "Secret deleted."
