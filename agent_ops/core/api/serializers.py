from django.contrib.contenttypes.models import ContentType
from django.urls import NoReverseMatch
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.reverse import reverse

from core.changelog import get_objectchange_target_url
from core.models import ObjectChange


class NestedContentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentType
        fields = ("id", "app_label", "model")


class ObjectChangeSerializer(serializers.HyperlinkedModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="api:changelog-detail")
    action_display = serializers.CharField(source="get_action_display", read_only=True)
    changed_object_type = NestedContentTypeSerializer(read_only=True)
    related_object_type = NestedContentTypeSerializer(read_only=True)
    changed_object_url = serializers.SerializerMethodField()
    related_object_url = serializers.SerializerMethodField()
    user = serializers.SerializerMethodField()

    class Meta:
        model = ObjectChange
        fields = (
            "id",
            "url",
            "time",
            "action",
            "action_display",
            "user",
            "user_name",
            "request_id",
            "changed_object_type",
            "changed_object_id",
            "changed_object_url",
            "related_object_type",
            "related_object_id",
            "related_object_url",
            "object_repr",
            "prechange_data",
            "postchange_data",
        )
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_user(self, obj):
        if obj.user is None:
            return None
        return {
            "id": obj.user_id,
            "username": obj.user.get_username(),
        }

    def _absolute_url(self, path):
        if not path:
            return None
        request = self.context.get("request")
        if request is None:
            return path
        return request.build_absolute_uri(path)

    @extend_schema_field(OpenApiTypes.URI)
    def get_changed_object_url(self, obj):
        return self._absolute_url(get_objectchange_target_url(obj))

    @extend_schema_field(OpenApiTypes.URI)
    def get_related_object_url(self, obj):
        if not obj.related_object_type_id or not obj.related_object_id:
            return None
        try:
            path = reverse(
                f"{obj.related_object_type.model}_changelog",
                args=[obj.related_object_id],
                request=self.context.get("request"),
            )
        except NoReverseMatch:
            return None
        return self._absolute_url(path)
