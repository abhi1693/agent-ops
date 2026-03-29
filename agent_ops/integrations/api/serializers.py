from rest_framework import serializers

from agent_ops.api.fields import SerializedPKRelatedField
from agent_ops.api.serializers import ValidatedModelSerializer
from integrations.models import Secret
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
