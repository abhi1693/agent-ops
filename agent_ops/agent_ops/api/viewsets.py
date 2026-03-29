from functools import cached_property

from rest_framework import mixins
from rest_framework.viewsets import GenericViewSet


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


class ReadOnlyModelViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    BaseViewSet,
):
    pass


class ModelViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    BaseViewSet,
):
    pass
