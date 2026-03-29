from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from rest_framework import serializers

from users.models import Group, ObjectPermission, Token, User


class UserSerializer(serializers.HyperlinkedModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="api:users-api:user-detail")
    groups = serializers.PrimaryKeyRelatedField(queryset=Group.objects.all().order_by("name"), many=True, required=False)
    object_permissions = serializers.PrimaryKeyRelatedField(
        queryset=ObjectPermission.objects.all().order_by("name"),
        many=True,
        required=False,
    )
    user_permissions = serializers.PrimaryKeyRelatedField(
        queryset=Permission.objects.all().order_by("content_type__app_label", "content_type__model", "codename"),
        many=True,
        required=False,
    )
    password = serializers.CharField(write_only=True, required=False, allow_blank=False)

    class Meta:
        model = User
        fields = (
            "id",
            "url",
            "username",
            "display_name",
            "first_name",
            "last_name",
            "email",
            "is_staff",
            "is_active",
            "is_superuser",
            "groups",
            "object_permissions",
            "user_permissions",
            "password",
            "date_joined",
            "last_login",
        )
        read_only_fields = ("id", "url", "date_joined", "last_login")

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError({"password": "This field is required."})
        return attrs

    def create(self, validated_data):
        groups = validated_data.pop("groups", [])
        object_permissions = validated_data.pop("object_permissions", [])
        user_permissions = validated_data.pop("user_permissions", [])
        password = validated_data.pop("password")

        user = User(**validated_data)
        user.set_password(password)
        user.save()
        user.groups.set(groups)
        user.object_permissions.set(object_permissions)
        user.user_permissions.set(user_permissions)
        return user

    def update(self, instance, validated_data):
        groups = validated_data.pop("groups", None)
        object_permissions = validated_data.pop("object_permissions", None)
        user_permissions = validated_data.pop("user_permissions", None)
        password = validated_data.pop("password", None)

        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.save()

        if groups is not None:
            instance.groups.set(groups)
        if object_permissions is not None:
            instance.object_permissions.set(object_permissions)
        if user_permissions is not None:
            instance.user_permissions.set(user_permissions)

        return instance


class GroupSerializer(serializers.HyperlinkedModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="api:users-api:group-detail")
    permissions = serializers.PrimaryKeyRelatedField(
        queryset=Permission.objects.all().order_by("content_type__app_label", "content_type__model", "codename"),
        many=True,
        required=False,
    )
    object_permissions = serializers.PrimaryKeyRelatedField(
        queryset=ObjectPermission.objects.all().order_by("name"),
        many=True,
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


class ObjectPermissionSerializer(serializers.HyperlinkedModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="api:users-api:objectpermission-detail")
    content_types = serializers.PrimaryKeyRelatedField(
        queryset=ContentType.objects.all().order_by("app_label", "model"),
        many=True,
    )
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
            "content_types",
            "actions",
            "constraints",
        )

    def validate_actions(self, value):
        if len(set(value)) != len(value):
            raise serializers.ValidationError("Duplicate actions are not allowed.")
        return value

    def create(self, validated_data):
        content_types = validated_data.pop("content_types", [])
        instance = ObjectPermission.objects.create(**validated_data)
        instance.content_types.set(content_types)
        return instance

    def update(self, instance, validated_data):
        content_types = validated_data.pop("content_types", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if content_types is not None:
            instance.content_types.set(content_types)
        return instance


class TokenSerializer(serializers.HyperlinkedModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="api:users-api:token-detail")
    user = serializers.SlugRelatedField(slug_field="username", read_only=True)
    identifier = serializers.CharField(source="masked_key", read_only=True)
    plaintext_token = serializers.CharField(read_only=True)

    class Meta:
        model = Token
        fields = (
            "id",
            "url",
            "user",
            "description",
            "identifier",
            "plaintext_token",
            "created",
            "expires",
            "last_used",
            "enabled",
            "write_enabled",
        )
        read_only_fields = ("id", "url", "user", "identifier", "plaintext_token", "created", "last_used")

    def validate_expires(self, value):
        if value is not None and self.instance is None and value <= timezone.now():
            raise serializers.ValidationError("Expiration time must be in the future.")
        return value
