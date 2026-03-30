from django.core.exceptions import ValidationError
from django.db.models import Count, Prefetch

from core.generic_views import (
    ObjectChangeLogView,
    ObjectDeleteView,
    ObjectEditView,
    ObjectListView,
    ObjectView,
)
from integrations import filtersets, tables
from integrations.forms import SecretForm, SecretGroupAssignmentForm, SecretGroupForm
from integrations.models import Secret, SecretGroup, SecretGroupAssignment
from tenancy.mixins import (
    RestrictedObjectChangeLogMixin,
    RestrictedObjectDeleteMixin,
    RestrictedObjectEditMixin,
    RestrictedObjectListMixin,
    RestrictedObjectViewMixin,
)
from users.restrictions import has_model_action_permission


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


class SecretGroupListView(RestrictedObjectListMixin, ObjectListView):
    queryset = SecretGroup.objects.select_related("organization", "workspace", "environment")
    table = tables.SecretGroupTable
    filterset = filtersets.SecretGroupFilterSet
    template_name = "integrations/secretgroup_list.html"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("organization", "workspace", "environment")
            .order_by("organization__name", "workspace__name", "environment__name", "name")
        )


class SecretGroupDetailView(RestrictedObjectViewMixin, ObjectView):
    model = SecretGroup
    template_name = "integrations/secretgroup_detail.html"

    def get_queryset(self):
        assignment_qs = SecretGroupAssignment.objects.select_related(
            "secret",
            "secret_group",
        ).order_by("order", "key", "secret__name")
        return (
            super()
            .get_queryset()
            .select_related("organization", "workspace", "environment")
            .prefetch_related(Prefetch("assignments", queryset=assignment_qs))
            .annotate(assignment_count=Count("assignments", distinct=True))
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["can_add_assignment"] = has_model_action_permission(
            SecretGroupAssignment,
            request=self.request,
            action="add",
        )
        return context


class SecretGroupChangelogView(RestrictedObjectChangeLogMixin, ObjectChangeLogView):
    model = SecretGroup
    queryset = SecretGroup.objects.select_related("organization", "workspace", "environment").order_by(
        "organization__name",
        "workspace__name",
        "environment__name",
        "name",
    )


class SecretGroupCreateView(RestrictedObjectEditMixin, ObjectEditView):
    model = SecretGroup
    form_class = SecretGroupForm
    success_message = "Secret group created."


class SecretGroupUpdateView(RestrictedObjectEditMixin, ObjectEditView):
    model = SecretGroup
    form_class = SecretGroupForm
    success_message = "Secret group updated."


class SecretGroupDeleteView(RestrictedObjectDeleteMixin, ObjectDeleteView):
    model = SecretGroup
    success_message = "Secret group deleted."


class SecretGroupAssignmentListView(RestrictedObjectListMixin, ObjectListView):
    queryset = SecretGroupAssignment.objects.select_related(
        "secret_group",
        "secret",
        "organization",
        "workspace",
        "environment",
    )
    table = tables.SecretGroupAssignmentTable
    filterset = filtersets.SecretGroupAssignmentFilterSet
    template_name = "integrations/secretgroupassignment_list.html"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("secret_group", "secret", "organization", "workspace", "environment")
            .order_by(
                "organization__name",
                "workspace__name",
                "environment__name",
                "secret_group__name",
                "order",
                "key",
            )
        )


class SecretGroupAssignmentDetailView(RestrictedObjectViewMixin, ObjectView):
    model = SecretGroupAssignment
    template_name = "integrations/secretgroupassignment_detail.html"

    def get_queryset(self):
        return super().get_queryset().select_related(
            "secret_group",
            "secret",
            "organization",
            "workspace",
            "environment",
        )


class SecretGroupAssignmentChangelogView(RestrictedObjectChangeLogMixin, ObjectChangeLogView):
    model = SecretGroupAssignment
    queryset = SecretGroupAssignment.objects.select_related(
        "secret_group",
        "secret",
        "organization",
        "workspace",
        "environment",
    ).order_by(
        "organization__name",
        "workspace__name",
        "environment__name",
        "secret_group__name",
        "order",
        "key",
    )


class SecretGroupAssignmentCreateView(RestrictedObjectEditMixin, ObjectEditView):
    model = SecretGroupAssignment
    form_class = SecretGroupAssignmentForm
    success_message = "Secret group assignment created."


class SecretGroupAssignmentUpdateView(RestrictedObjectEditMixin, ObjectEditView):
    model = SecretGroupAssignment
    form_class = SecretGroupAssignmentForm
    success_message = "Secret group assignment updated."


class SecretGroupAssignmentDeleteView(RestrictedObjectDeleteMixin, ObjectDeleteView):
    model = SecretGroupAssignment
    success_message = "Secret group assignment deleted."
