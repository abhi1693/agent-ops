from rest_framework import serializers
from rest_framework.reverse import reverse

from agent_ops.api.fields import SerializedPKRelatedField
from agent_ops.api.serializers import ValidatedModelSerializer
from automation.catalog.services import get_catalog_connection_type
from automation.models import Secret, SecretGroup, Workflow, WorkflowConnection, WorkflowRun
from tenancy.api.serializers import NestedOrganizationSerializer, NestedWorkspaceSerializer
from tenancy.models import Environment, Organization, Workspace
from users.restrictions import restrict_queryset


class NestedEnvironmentSerializer(serializers.ModelSerializer):
    organization = NestedOrganizationSerializer(read_only=True)
    workspace = NestedWorkspaceSerializer(read_only=True)

    class Meta:
        model = Environment
        fields = ("id", "name", "description", "organization", "workspace")


class NestedSecretGroupSerializer(serializers.ModelSerializer):
    organization = NestedOrganizationSerializer(read_only=True)
    workspace = NestedWorkspaceSerializer(read_only=True)
    environment = NestedEnvironmentSerializer(read_only=True)

    class Meta:
        model = SecretGroup
        fields = ("id", "name", "description", "organization", "workspace", "environment")


class NestedSecretSerializer(serializers.ModelSerializer):
    class Meta:
        model = Secret
        fields = ("id", "name", "provider", "enabled")


class SecretSerializer(ValidatedModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="api:automation-api:secret-detail")
    secret_group = SerializedPKRelatedField(
        serializer=NestedSecretGroupSerializer,
        queryset=SecretGroup.objects.select_related("organization", "workspace", "environment").order_by(
            "organization__name",
            "workspace__name",
            "environment__name",
            "name",
        ),
    )
    organization = NestedOrganizationSerializer(source="secret_group.organization", read_only=True)
    workspace = NestedWorkspaceSerializer(source="secret_group.workspace", read_only=True)
    environment = NestedEnvironmentSerializer(source="secret_group.environment", read_only=True)
    provider_display = serializers.SerializerMethodField()
    scope_label = serializers.CharField(read_only=True)

    class Meta:
        model = Secret
        fields = (
            "id",
            "url",
            "name",
            "description",
            "provider",
            "provider_display",
            "secret_group",
            "organization",
            "workspace",
            "environment",
            "scope_label",
            "parameters",
            "metadata",
            "enabled",
            "expires",
            "last_verified",
            "last_rotated",
        )
        read_only_fields = (
            "id",
            "url",
            "provider_display",
            "organization",
            "workspace",
            "environment",
            "scope_label",
            "last_verified",
            "last_rotated",
        )
        brief_fields = (
            "id",
            "url",
            "name",
            "provider",
            "provider_display",
            "secret_group",
            "organization",
            "workspace",
            "environment",
            "scope_label",
            "enabled",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is None:
            return
        self.fields["secret_group"].queryset = restrict_queryset(
            SecretGroup.objects.select_related("organization", "workspace", "environment").order_by(
                "organization__name",
                "workspace__name",
                "environment__name",
                "name",
            ),
            request=request,
            action="view",
        )

    def get_provider_display(self, obj) -> str:
        return obj.get_provider_display()


class SecretGroupSerializer(ValidatedModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="api:automation-api:secretgroup-detail")
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

    class Meta:
        model = SecretGroup
        fields = (
            "id",
            "url",
            "name",
            "description",
            "organization",
            "workspace",
            "environment",
            "scope_label",
        )
        read_only_fields = (
            "id",
            "url",
            "scope_label",
        )
        brief_fields = (
            "id",
            "url",
            "name",
            "organization",
            "workspace",
            "environment",
            "scope_label",
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
    secret_group = SerializedPKRelatedField(
        serializer=NestedSecretGroupSerializer,
        queryset=SecretGroup.objects.select_related("organization", "workspace", "environment").order_by(
            "organization__name",
            "workspace__name",
            "environment__name",
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
            "secret_group",
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
        self.fields["secret_group"].queryset = restrict_queryset(
            SecretGroup.objects.select_related("organization", "workspace", "environment").order_by(
                "organization__name",
                "workspace__name",
                "environment__name",
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
    credential_secret = SerializedPKRelatedField(
        serializer=NestedSecretSerializer,
        queryset=Secret.objects.select_related("secret_group__organization", "secret_group__workspace", "secret_group__environment").order_by(
            "secret_group__organization__name",
            "secret_group__workspace__name",
            "secret_group__environment__name",
            "secret_group__name",
            "name",
        ),
        required=False,
        allow_null=True,
    )
    scope_label = serializers.CharField(read_only=True)

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
            "credential_secret",
            "enabled",
            "auth_config",
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

    def validate(self, data):
        attrs = data.copy()
        connection_type = attrs.get("connection_type") or getattr(self.instance, "connection_type", None)
        if connection_type and not attrs.get("integration_id"):
            connection_definition = get_catalog_connection_type(connection_type)
            if connection_definition is not None:
                attrs["integration_id"] = connection_definition.integration_id
        return super().validate(attrs)
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
        self.fields["credential_secret"].queryset = restrict_queryset(
            Secret.objects.select_related("secret_group__organization", "secret_group__workspace", "secret_group__environment").order_by(
                "secret_group__organization__name",
                "secret_group__workspace__name",
                "secret_group__environment__name",
                "secret_group__name",
                "name",
            ),
            request=request,
            action="view",
        )


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
