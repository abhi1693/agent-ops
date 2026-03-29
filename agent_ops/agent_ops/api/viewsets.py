from functools import cached_property

from django.db import transaction
from rest_framework import mixins
from rest_framework.viewsets import GenericViewSet

from users.restrictions import get_action_for_method


class BaseViewSet(GenericViewSet):
    brief = False

    def initialize_request(self, request, *args, **kwargs):
        self.brief = request.method == "GET" and bool(request.GET.get("brief"))
        return super().initialize_request(request, *args, **kwargs)

    def get_serializer(self, *args, **kwargs):
        if isinstance(kwargs.get("data"), list):
            kwargs["many"] = True

        if self.brief_fields:
            kwargs["fields"] = self.brief_fields

        return super().get_serializer(*args, **kwargs)

    @cached_property
    def brief_fields(self):
        if self.brief:
            serializer_class = self.get_serializer_class()
            return getattr(serializer_class.Meta, "brief_fields", None)
        return None

    def get_permission_action(self):
        request = getattr(self, "request", None)
        if request is None:
            return "view"
        return get_action_for_method(request.method)

    def validate_saved_object_permissions(self, obj):
        return obj


class ModelViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    BaseViewSet,
):
    def perform_create(self, serializer):
        with transaction.atomic():
            obj = serializer.save()
            return self.validate_saved_object_permissions(obj)

    def perform_update(self, serializer):
        with transaction.atomic():
            obj = serializer.save()
            return self.validate_saved_object_permissions(obj)

    def perform_destroy(self, instance):
        self.validate_saved_object_permissions(instance)
        return super().perform_destroy(instance)
