from rest_framework import serializers

from agent_ops.api.fields import SerializedPKRelatedField
from agent_ops.api.serializers import ValidatedModelSerializer
from automation.models import Workflow, WorkflowRun
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
            "metadata",
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


class WorkflowRunSerializer(serializers.ModelSerializer):
    workflow = WorkflowSerializer(read_only=True, nested=True)
    organization = NestedOrganizationSerializer(read_only=True)
    workspace = NestedWorkspaceSerializer(read_only=True)
    environment = NestedEnvironmentSerializer(read_only=True)
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
            "scope_label",
            "trigger_mode",
            "status",
            "input_data",
            "output_data",
            "context_data",
            "step_results",
            "step_count",
            "error",
            "created",
            "last_updated",
            "finished_at",
        )
