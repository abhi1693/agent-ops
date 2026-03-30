from rest_framework import serializers

from agent_ops.api.fields import SerializedPKRelatedField
from agent_ops.api.serializers import ValidatedModelSerializer
from integrations.models import Secret, SecretGroup, SecretGroupAssignment
from tenancy.api.serializers import NestedOrganizationSerializer, NestedWorkspaceSerializer
from tenancy.models import Environment, Organization, Workspace
from users.restrictions import restrict_queryset


class NestedEnvironmentSerializer(serializers.ModelSerializer):
    organization = NestedOrganizationSerializer(read_only=True)
    workspace = NestedWorkspaceSerializer(read_only=True)

    class Meta:
        model = Environment
        fields = ("id", "name", "description", "organization", "workspace")


class SecretSerializer(ValidatedModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="api:integrations-api:secret-detail")
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

    def get_provider_display(self, obj) -> str:
        return obj.get_provider_display()


class SecretGroupSerializer(ValidatedModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="api:integrations-api:secretgroup-detail")
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


class NestedSecretGroupSerializer(serializers.ModelSerializer):
    organization = NestedOrganizationSerializer(read_only=True)
    workspace = NestedWorkspaceSerializer(read_only=True)
    environment = NestedEnvironmentSerializer(read_only=True)

    class Meta:
        model = SecretGroup
        fields = ("id", "name", "description", "organization", "workspace", "environment")


class NestedSecretSerializer(serializers.ModelSerializer):
    organization = NestedOrganizationSerializer(read_only=True)
    workspace = NestedWorkspaceSerializer(read_only=True)
    environment = NestedEnvironmentSerializer(read_only=True)
    provider_display = serializers.SerializerMethodField()

    class Meta:
        model = Secret
        fields = ("id", "name", "description", "provider", "provider_display", "organization", "workspace", "environment")

    def get_provider_display(self, obj) -> str:
        return obj.get_provider_display()


class SecretGroupAssignmentSerializer(ValidatedModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="api:integrations-api:secretgroupassignment-detail")
    secret_group = SerializedPKRelatedField(
        serializer=NestedSecretGroupSerializer,
        queryset=SecretGroup.objects.select_related("organization", "workspace", "environment").order_by(
            "organization__name",
            "workspace__name",
            "environment__name",
            "name",
        ),
    )
    secret = SerializedPKRelatedField(
        serializer=NestedSecretSerializer,
        queryset=Secret.objects.select_related("organization", "workspace", "environment").order_by(
            "organization__name",
            "workspace__name",
            "environment__name",
            "name",
        ),
    )
    organization = NestedOrganizationSerializer(read_only=True)
    workspace = NestedWorkspaceSerializer(read_only=True)
    environment = NestedEnvironmentSerializer(read_only=True)
    scope_label = serializers.CharField(read_only=True)

    class Meta:
        model = SecretGroupAssignment
        fields = (
            "id",
            "url",
            "secret_group",
            "secret",
            "organization",
            "workspace",
            "environment",
            "scope_label",
            "key",
            "required",
            "order",
            "created",
            "last_updated",
        )
        read_only_fields = (
            "id",
            "url",
            "organization",
            "workspace",
            "environment",
            "scope_label",
            "created",
            "last_updated",
        )
        brief_fields = (
            "id",
            "url",
            "secret_group",
            "secret",
            "key",
            "required",
            "order",
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
        self.fields["secret"].queryset = restrict_queryset(
            Secret.objects.select_related("organization", "workspace", "environment").order_by(
                "organization__name",
                "workspace__name",
                "environment__name",
                "name",
            ),
            request=request,
            action="view",
        )
