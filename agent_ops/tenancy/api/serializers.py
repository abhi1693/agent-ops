from rest_framework import serializers

from agent_ops.api.fields import SerializedPKRelatedField
from agent_ops.api.serializers import ValidatedModelSerializer
from tenancy.models import Environment, Organization, Workspace
from users.restrictions import restrict_queryset


class NestedOrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ("id", "name", "description")


class NestedWorkspaceSerializer(serializers.ModelSerializer):
    organization = NestedOrganizationSerializer(read_only=True)

    class Meta:
        model = Workspace
        fields = ("id", "name", "description", "organization")


class OrganizationSerializer(ValidatedModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="api:tenancy-api:organization-detail")
    workspace_count = serializers.IntegerField(read_only=True)
    environment_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Organization
        fields = (
            "id",
            "url",
            "name",
            "description",
            "workspace_count",
            "environment_count",
        )
        read_only_fields = ("id", "url", "workspace_count", "environment_count")
        brief_fields = ("id", "url", "name", "description")


class WorkspaceSerializer(ValidatedModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="api:tenancy-api:workspace-detail")
    organization = SerializedPKRelatedField(
        serializer=NestedOrganizationSerializer,
        queryset=Organization.objects.order_by("name"),
    )
    environment_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Workspace
        fields = (
            "id",
            "url",
            "name",
            "description",
            "organization",
            "environment_count",
        )
        read_only_fields = ("id", "url", "environment_count")
        brief_fields = ("id", "url", "name", "description", "organization")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        queryset = Organization.objects.order_by("name")
        if request is not None:
            queryset = restrict_queryset(queryset, request=request, action="view")
        self.fields["organization"].queryset = queryset


class EnvironmentSerializer(ValidatedModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="api:tenancy-api:environment-detail")
    organization = NestedOrganizationSerializer(read_only=True)
    workspace = SerializedPKRelatedField(
        serializer=NestedWorkspaceSerializer,
        queryset=Workspace.objects.select_related("organization").order_by("organization__name", "name"),
    )

    class Meta:
        model = Environment
        fields = (
            "id",
            "url",
            "name",
            "description",
            "organization",
            "workspace",
        )
        read_only_fields = ("id", "url", "organization")
        brief_fields = ("id", "url", "name", "description", "organization", "workspace")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        queryset = Workspace.objects.select_related("organization").order_by(
            "organization__name",
            "name",
        )
        if request is not None:
            queryset = restrict_queryset(queryset, request=request, action="view")
        self.fields["workspace"].queryset = queryset
