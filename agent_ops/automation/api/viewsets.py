from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.routers import APIRootView
from rest_framework import status

from agent_ops.api.viewsets import ReadOnlyModelViewSet
from agent_ops.api.permissions import ObjectActionPermission, TokenPermissions
from agent_ops.api.viewsets import ModelViewSet
from automation import filtersets
from automation.catalog.payloads import build_workflow_catalog_payload
from automation.models import Workflow, WorkflowConnection, WorkflowRun
from automation.runtime import enqueue_workflow
from users.restrictions import assert_object_action_allowed, restrict_queryset

from .serializers import (
    WorkflowConnectionSerializer,
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
                "workflow-runs": reverse("api:automation-api:workflowrun-list", request=request),
                "workflow-connections": reverse("api:automation-api:workflowconnection-list", request=request),
                "workflow-catalog": reverse("api:automation-api:workflowcatalog-list", request=request),
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
        run = enqueue_workflow(
            workflow,
            input_data=serializer.validated_data.get("input_data") or {},
            actor=request.user,
        )
        return Response(
            WorkflowRunSerializer(run, context=self.get_serializer_context()).data,
            status=status.HTTP_202_ACCEPTED,
        )


class WorkflowRunViewSet(ReadOnlyModelViewSet):
    serializer_class = WorkflowRunSerializer
    ordering_fields = ("created", "last_updated", "finished_at", "status")
    permission_classes = [TokenPermissions, ObjectActionPermission]

    def get_queryset(self):
        queryset = WorkflowRun.objects.select_related(
            "workflow",
            "workflow__organization",
            "workflow__workspace",
            "workflow__environment",
            "organization",
            "workspace",
            "environment",
            "workflow_version",
        ).order_by("-created")
        return restrict_queryset(
            queryset,
            request=self.request,
            action=self.get_permission_action(),
        )


class WorkflowConnectionViewSet(RestrictedAutomationViewSet):
    serializer_class = WorkflowConnectionSerializer
    filterset_class = filtersets.WorkflowConnectionFilterSet
    ordering_fields = ("name", "integration_id", "connection_type", "enabled", "created", "last_updated")
    permission_classes = [TokenPermissions, ObjectActionPermission]

    def get_queryset(self):
        queryset = WorkflowConnection.objects.select_related(
            "organization",
            "workspace",
            "environment",
            "state",
        ).order_by(
            "organization__name",
            "workspace__name",
            "environment__name",
            "integration_id",
            "name",
        )
        return restrict_queryset(
            queryset,
            request=self.request,
            action=self.get_permission_action(),
        )


class WorkflowCatalogViewSet(ViewSet):
    permission_classes = [TokenPermissions]

    @extend_schema(responses=dict)
    def list(self, request):
        return Response(build_workflow_catalog_payload())
