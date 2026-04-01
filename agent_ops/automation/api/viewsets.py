from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.routers import APIRootView
from rest_framework import status

from agent_ops.api.permissions import ObjectActionPermission, TokenPermissions
from agent_ops.api.viewsets import ModelViewSet
from automation import filtersets
from automation.models import Secret, SecretGroup, Workflow
from automation.runtime import execute_workflow
from users.restrictions import assert_object_action_allowed, restrict_queryset

from .serializers import (
    SecretGroupSerializer,
    SecretSerializer,
    WorkflowExecuteSerializer,
    WorkflowRunSerializer,
    WorkflowSerializer,
)


class AutomationRootView(APIRootView):
    permission_classes = [TokenPermissions]

    def get_view_name(self):
        return "Automation"

    @extend_schema(exclude=True)
    def get(self, request, *args, **kwargs):
        return Response(
            {
                "workflows": reverse("api:automation-api:workflow-list", request=request),
                "secrets": reverse("api:automation-api:secret-list", request=request),
                "secret-groups": reverse("api:automation-api:secretgroup-list", request=request),
            }
        )


class RestrictedAutomationViewSet(ModelViewSet):
    def validate_saved_object_permissions(self, obj):
        assert_object_action_allowed(
            obj,
            request=self.request,
            action=self.get_permission_action(),
        )
        return obj


class WorkflowViewSet(RestrictedAutomationViewSet):
    serializer_class = WorkflowSerializer
    filterset_class = filtersets.WorkflowFilterSet
    ordering_fields = ("name", "enabled", "created", "last_updated")
    permission_classes = [TokenPermissions, ObjectActionPermission]

    def get_permission_action(self):
        if getattr(self, "action", None) == "execute":
            return "change"
        return super().get_permission_action()

    def get_queryset(self):
        queryset = Workflow.objects.select_related("organization", "workspace", "environment").order_by(
            "organization__name",
            "workspace__name",
            "environment__name",
            "name",
        )
        return restrict_queryset(
            queryset,
            request=self.request,
            action=self.get_permission_action(),
        )

    @extend_schema(
        request=WorkflowExecuteSerializer,
        responses=WorkflowRunSerializer,
    )
    @action(detail=True, methods=["post"])
    def execute(self, request, *args, **kwargs):
        workflow = self.get_object()
        assert_object_action_allowed(workflow, request=request, action="change")
        serializer = WorkflowExecuteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = execute_workflow(
            workflow,
            input_data=serializer.validated_data.get("input_data") or {},
            actor=request.user,
        )
        return Response(
            WorkflowRunSerializer(run, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )


class SecretViewSet(RestrictedAutomationViewSet):
    serializer_class = SecretSerializer
    filterset_class = filtersets.SecretFilterSet
    ordering_fields = ("name", "provider", "enabled", "expires")
    permission_classes = [TokenPermissions, ObjectActionPermission]

    def get_queryset(self):
        queryset = Secret.objects.select_related(
            "secret_group__organization",
            "secret_group__workspace",
            "secret_group__environment",
        ).order_by(
            "secret_group__organization__name",
            "secret_group__workspace__name",
            "secret_group__environment__name",
            "secret_group__name",
            "name",
        )
        return restrict_queryset(
            queryset,
            request=self.request,
            action=self.get_permission_action(),
        )


class SecretGroupViewSet(RestrictedAutomationViewSet):
    serializer_class = SecretGroupSerializer
    filterset_class = filtersets.SecretGroupFilterSet
    ordering_fields = ("name",)
    permission_classes = [TokenPermissions, ObjectActionPermission]

    def get_queryset(self):
        queryset = SecretGroup.objects.select_related("organization", "workspace", "environment").order_by(
            "organization__name",
            "workspace__name",
            "environment__name",
            "name",
        )
        return restrict_queryset(
            queryset,
            request=self.request,
            action=self.get_permission_action(),
        )
