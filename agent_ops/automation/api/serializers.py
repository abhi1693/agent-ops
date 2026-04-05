from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.reverse import reverse
from rest_framework.serializers import as_serializer_error

from agent_ops.api.fields import SerializedPKRelatedField
from agent_ops.api.serializers import ValidatedModelSerializer
from automation.catalog.services import get_catalog_connection_type
from automation.models import Workflow, WorkflowConnection, WorkflowConnectionState, WorkflowRun
from tenancy.api.serializers import NestedOrganizationSerializer, NestedWorkspaceSerializer
from tenancy.models import Environment, Organization, Workspace
from users.restrictions import restrict_queryset


class NestedEnvironmentSerializer(serializers.ModelSerializer):
    organization = NestedOrganizationSerializer(read_only=True)
    workspace = NestedWorkspaceSerializer(read_only=True)

    class Meta:
        model = Environment
        fields = ("id", "name", "description", "organization", "workspace")


class WorkflowSerializer(ValidatedModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="api:automation-api:workflow-detail")
    organization = SerializedPKRelatedField(
        serializer=NestedOrganizationSerializer,
        queryset=Organization.objects.order_by("name"),
        required=False,
        allow_null=True,
    )
    workspace = SerializedPKRelatedField(
        serializer=NestedWorkspaceSerializer,
        queryset=Workspace.objects.select_related("organization").order_by("organization__name", "name"),
        required=False,
        allow_null=True,
    )
    environment = SerializedPKRelatedField(
        serializer=NestedEnvironmentSerializer,
        queryset=Environment.objects.select_related("organization", "workspace").order_by(
            "organization__name",
            "workspace__name",
            "name",
        ),
        required=False,
        allow_null=True,
    )
    scope_label = serializers.CharField(read_only=True)
    node_count = serializers.IntegerField(read_only=True)
    edge_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Workflow
        fields = (
            "id",
            "url",
            "name",
            "description",
            "organization",
            "workspace",
            "environment",
            "scope_label",
            "enabled",
            "definition",
            "node_count",
            "edge_count",
            "created",
            "last_updated",
        )
        read_only_fields = (
            "id",
            "url",
            "scope_label",
            "node_count",
            "edge_count",
            "created",
            "last_updated",
        )
        brief_fields = (
            "id",
            "url",
            "name",
            "organization",
            "workspace",
            "environment",
            "scope_label",
            "enabled",
            "node_count",
            "edge_count",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is None:
            return
        self.fields["organization"].queryset = restrict_queryset(
            Organization.objects.order_by("name"),
            request=request,
            action="view",
        )
        self.fields["workspace"].queryset = restrict_queryset(
            Workspace.objects.select_related("organization").order_by("organization__name", "name"),
            request=request,
            action="view",
        )
        self.fields["environment"].queryset = restrict_queryset(
            Environment.objects.select_related("organization", "workspace").order_by(
                "organization__name",
                "workspace__name",
                "name",
            ),
            request=request,
            action="view",
        )


class WorkflowExecuteSerializer(serializers.Serializer):
    input_data = serializers.JSONField(required=False, default=dict)


class WorkflowConnectionSerializer(ValidatedModelSerializer):
    organization = SerializedPKRelatedField(
        serializer=NestedOrganizationSerializer,
        queryset=Organization.objects.order_by("name"),
        required=False,
        allow_null=True,
    )
    workspace = SerializedPKRelatedField(
        serializer=NestedWorkspaceSerializer,
        queryset=Workspace.objects.select_related("organization").order_by("organization__name", "name"),
        required=False,
        allow_null=True,
    )
    environment = SerializedPKRelatedField(
        serializer=NestedEnvironmentSerializer,
        queryset=Environment.objects.select_related("organization", "workspace").order_by(
            "organization__name",
            "workspace__name",
            "name",
        ),
        required=False,
        allow_null=True,
    )
    scope_label = serializers.CharField(read_only=True)
    data = serializers.JSONField(write_only=True, required=False)
    state_values = serializers.JSONField(write_only=True, required=False)
    state_summary = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = WorkflowConnection
        fields = (
            "id",
            "name",
            "description",
            "integration_id",
            "connection_type",
            "organization",
            "workspace",
            "environment",
            "enabled",
            "data",
            "state_values",
            "state_summary",
            "metadata",
            "scope_label",
        )
        read_only_fields = ("id", "scope_label")
        brief_fields = (
            "id",
            "name",
            "integration_id",
            "connection_type",
            "organization",
            "workspace",
            "environment",
            "enabled",
            "state_summary",
            "scope_label",
        )
        extra_kwargs = {
            "integration_id": {"read_only": True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is None:
            return
        self.fields["organization"].queryset = restrict_queryset(
            Organization.objects.order_by("name"),
            request=request,
            action="view",
        )
        self.fields["workspace"].queryset = restrict_queryset(
            Workspace.objects.select_related("organization").order_by("organization__name", "name"),
            request=request,
            action="view",
        )
        self.fields["environment"].queryset = restrict_queryset(
            Environment.objects.select_related("organization", "workspace").order_by(
                "organization__name",
                "workspace__name",
                "name",
            ),
            request=request,
            action="view",
        )

    def validate(self, data):
        attrs = data.copy()
        connection_type = attrs.get("connection_type") or getattr(self.instance, "connection_type", None)
        if connection_type and not attrs.get("integration_id"):
            connection_definition = get_catalog_connection_type(connection_type)
            if connection_definition is not None:
                attrs["integration_id"] = connection_definition.integration_id

        data_values = attrs.pop("data", None)
        state_values = attrs.pop("state_values", None)

        model_attrs = attrs.copy()
        opts = self.Meta.model._meta
        for field in [*opts.local_many_to_many, *opts.related_objects]:
            model_attrs.pop(field.name, None)

        if self.instance is None:
            instance = self.Meta.model(**model_attrs)
        else:
            instance = self.instance
            for key, value in model_attrs.items():
                setattr(instance, key, value)

        if data_values is not None:
            instance.set_data_values(data_values)
        try:
            instance.full_clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(as_serializer_error(exc)) from exc

        attrs["data"] = data_values
        attrs["state_values"] = state_values
        return attrs

    def get_state_summary(self, obj):
        state = getattr(obj, "state", None)
        return state.summary if state is not None else None

    def create(self, validated_data):
        data_values = validated_data.pop("data", None)
        state_values = validated_data.pop("state_values", None)
        connection = super().create(validated_data)
        if data_values is not None:
            connection.set_data_values(data_values)
            connection.save(update_fields=("data",))
        self._save_state_values(connection, state_values)
        return connection

    def update(self, instance, validated_data):
        data_values = validated_data.pop("data", None)
        state_values = validated_data.pop("state_values", None)
        connection = super().update(instance, validated_data)
        if data_values is not None:
            connection.set_data_values(data_values)
            connection.save(update_fields=("data",))
        self._save_state_values(connection, state_values)
        return connection

    def _save_state_values(self, connection, state_values):
        if state_values is None:
            return
        state, _ = WorkflowConnectionState.objects.get_or_create(connection=connection)
        state.state_values = state_values or {}
        state.full_clean()
        state.save()


class WorkflowRunSerializer(serializers.ModelSerializer):
    workflow = WorkflowSerializer(read_only=True, nested=True)
    organization = NestedOrganizationSerializer(read_only=True)
    workspace = NestedWorkspaceSerializer(read_only=True)
    environment = NestedEnvironmentSerializer(read_only=True)
    status_url = serializers.SerializerMethodField()
    scope_label = serializers.CharField(read_only=True)
    step_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = WorkflowRun
        fields = (
            "id",
            "workflow",
            "organization",
            "workspace",
            "environment",
            "status_url",
            "scope_label",
            "trigger_mode",
            "trigger_metadata",
            "execution_mode",
            "target_node_id",
            "status",
            "job_id",
            "queue_name",
            "input_data",
            "output_data",
            "context_data",
            "scheduler_state",
            "step_results",
            "step_count",
            "error",
            "created",
            "last_updated",
            "finished_at",
        )

    def get_status_url(self, obj) -> str | None:
        request = self.context.get("request")
        if request is None:
            return None
        return reverse("api:automation-api:workflowrun-detail", args=[obj.pk], request=request)
