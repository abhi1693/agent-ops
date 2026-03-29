from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from rest_framework import serializers

from agent_ops.api.fields import SerializedPKRelatedField
from agent_ops.api.serializers import BaseModelSerializer, ValidatedModelSerializer
from tenancy.models import Environment, Organization, Workspace
from users.models import Group, Membership, ObjectPermission, Token, User


class NestedContentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentType
        fields = ("id", "app_label", "model")


class NestedPermissionSerializer(serializers.ModelSerializer):
    content_type = NestedContentTypeSerializer(read_only=True)

    class Meta:
        model = Permission
        fields = ("id", "name", "codename", "content_type")


class NestedObjectPermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ObjectPermission
        fields = ("id", "name", "description", "enabled", "actions")


class NestedGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ("id", "name", "description")


class NestedUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "first_name", "last_name", "email")


class MembershipOrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ("id", "name", "description")


class MembershipWorkspaceSerializer(serializers.ModelSerializer):
    organization = MembershipOrganizationSerializer(read_only=True)

    class Meta:
        model = Workspace
        fields = ("id", "name", "description", "organization")


class MembershipEnvironmentSerializer(serializers.ModelSerializer):
    workspace = MembershipWorkspaceSerializer(read_only=True)

    class Meta:
        model = Environment
        fields = ("id", "name", "description", "workspace")


class NestedMembershipSerializer(serializers.ModelSerializer):
    organization = MembershipOrganizationSerializer(read_only=True)
    workspace = MembershipWorkspaceSerializer(read_only=True)
    environment = MembershipEnvironmentSerializer(read_only=True)
    scope_type = serializers.CharField(read_only=True)
    scope_label = serializers.CharField(read_only=True)

    class Meta:
        model = Membership
        fields = (
            "id",
            "scope_type",
            "scope_label",
            "is_default",
            "is_active",
            "organization",
            "workspace",
            "environment",
        )


class UserSerializer(ValidatedModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="api:users-api:user-detail")
    groups = SerializedPKRelatedField(
        serializer=NestedGroupSerializer,
        many=True,
        queryset=Group.objects.all(),
        required=False,
    )
    object_permissions = SerializedPKRelatedField(
        serializer=NestedObjectPermissionSerializer,
        many=True,
        queryset=ObjectPermission.objects.all(),
        required=False,
    )
    user_permissions = SerializedPKRelatedField(
        serializer=NestedPermissionSerializer,
        many=True,
        queryset=Permission.objects.all(),
        required=False,
    )
    memberships = NestedMembershipSerializer(many=True, read_only=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=False)

    class Meta:
        model = User
        fields = (
            "id",
            "url",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_staff",
            "is_superuser",
            "is_active",
            "date_joined",
            "last_login",
            "groups",
            "memberships",
            "object_permissions",
            "user_permissions",
            "password",
        )
        read_only_fields = ("id", "url", "date_joined", "last_login")
        brief_fields = ("id", "url", "username", "first_name", "last_name", "email")

    def validate(self, attrs):
        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError({"password": "This field is required."})
        return super().validate(attrs)

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = super().create(validated_data)
        if password:
            user.set_password(password)
            user.save(update_fields=("password",))
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save(update_fields=("password",))
        return user


class GroupSerializer(ValidatedModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="api:users-api:group-detail")
    permissions = SerializedPKRelatedField(
        serializer=NestedPermissionSerializer,
        many=True,
        queryset=Permission.objects.all(),
        required=False,
    )
    object_permissions = SerializedPKRelatedField(
        serializer=NestedObjectPermissionSerializer,
        many=True,
        queryset=ObjectPermission.objects.all(),
        required=False,
    )

    class Meta:
        model = Group
        fields = (
            "id",
            "url",
            "name",
            "description",
            "permissions",
            "object_permissions",
        )
        brief_fields = ("id", "url", "name", "description")


class ObjectPermissionSerializer(ValidatedModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="api:users-api:objectpermission-detail")
    content_types = SerializedPKRelatedField(
        serializer=NestedContentTypeSerializer,
        many=True,
        queryset=ContentType.objects.all(),
    )
    groups = NestedGroupSerializer(many=True, read_only=True)
    memberships = NestedMembershipSerializer(many=True, read_only=True)
    users = NestedUserSerializer(many=True, read_only=True)
    actions = serializers.ListField(
        child=serializers.ChoiceField(choices=ObjectPermission.ActionChoices.choices),
        allow_empty=False,
    )
    constraints = serializers.JSONField(required=False, allow_null=True)

    class Meta:
        model = ObjectPermission
        fields = (
            "id",
            "url",
            "name",
            "description",
            "enabled",
            "actions",
            "constraints",
            "content_types",
            "groups",
            "memberships",
            "users",
        )
        brief_fields = ("id", "url", "name", "description", "enabled", "actions")

    def validate_actions(self, value):
        if len(set(value)) != len(value):
            raise serializers.ValidationError("Duplicate actions are not allowed.")
        return value


class TokenSerializer(BaseModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="api:users-api:token-detail")
    identifier = serializers.CharField(source="masked_key", read_only=True)
    plaintext_token = serializers.CharField(read_only=True)
    user = NestedUserSerializer(read_only=True)
    scope_membership = SerializedPKRelatedField(
        serializer=NestedMembershipSerializer,
        queryset=Membership.objects.none(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Token
        fields = (
            "id",
            "url",
            "identifier",
            "user",
            "description",
            "scope_membership",
            "created",
            "expires",
            "last_used",
            "enabled",
            "write_enabled",
            "plaintext_token",
        )
        read_only_fields = (
            "id",
            "url",
            "identifier",
            "user",
            "plaintext_token",
            "scope_membership",
            "created",
            "last_used",
        )
        brief_fields = (
            "id",
            "url",
            "identifier",
            "description",
            "scope_membership",
            "enabled",
            "write_enabled",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        queryset = Membership.objects.none()
        if request and request.user.is_authenticated:
            queryset = request.user.get_active_memberships()
        self.fields["scope_membership"].queryset = queryset

    def validate_expires(self, value):
        if value is not None and value <= timezone.now():
            raise serializers.ValidationError("Expiration time must be in the future.")
        return value

    def validate_scope_membership(self, value):
        request = self.context.get("request")
        if value is not None and request and value.user_id != request.user.id:
            raise serializers.ValidationError("Selected membership must belong to the current user.")
        return value


class MembershipSerializer(ValidatedModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="api:users-api:membership-detail")
    user = SerializedPKRelatedField(
        serializer=NestedUserSerializer,
        queryset=User.objects.order_by("username"),
    )
    organization = SerializedPKRelatedField(
        serializer=MembershipOrganizationSerializer,
        queryset=Organization.objects.order_by("name"),
    )
    workspace = SerializedPKRelatedField(
        serializer=MembershipWorkspaceSerializer,
        queryset=Workspace.objects.select_related("organization").order_by("organization__name", "name"),
        required=False,
        allow_null=True,
    )
    environment = SerializedPKRelatedField(
        serializer=MembershipEnvironmentSerializer,
        queryset=Environment.objects.select_related("organization", "workspace").order_by(
            "organization__name", "workspace__name", "name"
        ),
        required=False,
        allow_null=True,
    )
    groups = SerializedPKRelatedField(
        serializer=NestedGroupSerializer,
        many=True,
        queryset=Group.objects.order_by("name"),
        required=False,
    )
    object_permissions = SerializedPKRelatedField(
        serializer=NestedObjectPermissionSerializer,
        many=True,
        queryset=ObjectPermission.objects.order_by("name"),
        required=False,
    )
    scope_type = serializers.CharField(read_only=True)
    scope_label = serializers.CharField(read_only=True)

    class Meta:
        model = Membership
        fields = (
            "id",
            "url",
            "user",
            "description",
            "is_active",
            "is_default",
            "organization",
            "workspace",
            "environment",
            "scope_type",
            "scope_label",
            "groups",
            "object_permissions",
        )
        read_only_fields = ("id", "url", "scope_type", "scope_label")
        brief_fields = (
            "id",
            "url",
            "user",
            "is_active",
            "is_default",
            "scope_type",
            "scope_label",
        )
