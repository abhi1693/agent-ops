from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.routers import APIRootView

from agent_ops.api.permissions import ObjectActionPermission, TokenPermissions
from agent_ops.api.viewsets import ModelViewSet
from integrations import filtersets
from integrations.models import Secret
from users.restrictions import (
    assert_object_action_allowed,
    get_action_for_method,
    restrict_queryset,
)

from .serializers import SecretSerializer


class IntegrationsRootView(APIRootView):
    permission_classes = [TokenPermissions]

    def get_view_name(self):
        return "Integrations"

    @extend_schema(exclude=True)
    def get(self, request, *args, **kwargs):
        return Response(
            {
                "secrets": reverse("api:integrations-api:secret-list", request=request),
            }
        )


class RestrictedIntegrationsViewSet(ModelViewSet):
    def validate_saved_object_permissions(self, obj):
        assert_object_action_allowed(
            obj,
            request=self.request,
            action=self.get_permission_action(),
        )
        return obj


class SecretViewSet(RestrictedIntegrationsViewSet):
    serializer_class = SecretSerializer
    filterset_class = filtersets.SecretFilterSet
    ordering_fields = ("name", "provider", "enabled", "expires")
    permission_classes = [TokenPermissions, ObjectActionPermission]

    def get_queryset(self):
        queryset = Secret.objects.select_related("organization", "workspace", "environment").order_by(
            "organization__name",
            "workspace__name",
            "environment__name",
            "name",
        )
        return restrict_queryset(
            queryset,
            request=self.request,
            action=get_action_for_method(self.request.method),
        )
