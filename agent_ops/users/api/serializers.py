from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from rest_framework import serializers

from agent_ops.api.fields import SerializedPKRelatedField
from agent_ops.api.serializers import BaseModelSerializer, ValidatedModelSerializer
from users.models import Group, ObjectPermission, Token, User


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
        fields = ("id", "username", "display_name", "first_name", "last_name", "email")


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
            "display_name",
            "is_staff",
            "is_superuser",
            "is_active",
            "date_joined",
            "last_login",
            "groups",
            "object_permissions",
            "user_permissions",
            "password",
        )
        read_only_fields = ("id", "url", "date_joined", "last_login")
        brief_fields = ("id", "url", "username", "display_name", "first_name", "last_name", "email")

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

    class Meta:
        model = Token
        fields = (
            "id",
            "url",
            "identifier",
            "user",
            "description",
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
            "created",
            "last_used",
        )
        brief_fields = ("id", "url", "identifier", "description", "enabled", "write_enabled")

    def validate_expires(self, value):
        if value is not None and value <= timezone.now():
            raise serializers.ValidationError("Expiration time must be in the future.")
        return value
