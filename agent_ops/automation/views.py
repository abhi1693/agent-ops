import json

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from automation import filtersets, tables
from automation.catalog.services import (
    WORKFLOW_DESIGNER_CATALOG_ONLY_MESSAGE,
    get_catalog_connection_type,
    workflow_definition_supports_catalog_designer,
)
from automation.catalog.payloads import build_workflow_catalog_payload
from automation.catalog.webhooks import prepare_catalog_webhook_request
from automation.forms import (
    SecretForm,
    SecretGroupForm,
    WorkflowConnectionForm,
    WorkflowDesignerForm,
    WorkflowForm,
    WorkflowRunForm,
)
from automation.models import Secret, SecretGroup, Workflow, WorkflowConnection, WorkflowRun, WorkflowStepRun, WorkflowVersion
from automation.primitives import normalize_workflow_definition_nodes
from automation.runtime import enqueue_workflow, execute_workflow
from automation.workflow_connections import split_workflow_edges
from core.generic_views import (
    ObjectChangeLogView,
    ObjectDeleteView,
    ObjectEditView,
    ObjectListView,
    ObjectView,
)
from tenancy.mixins import (
    RestrictedObjectChangeLogMixin,
    RestrictedObjectDeleteMixin,
    RestrictedObjectEditMixin,
    RestrictedObjectListMixin,
    RestrictedObjectViewMixin,
)
from users.restrictions import assert_object_action_allowed


def _pretty_json(value):
    if value in (None, "", {}, []):
        return None
    return json.dumps(value, indent=2, sort_keys=True)


def _flatten_validation_error(error: ValidationError) -> str:
    if hasattr(error, "message_dict"):
        parts = []
        for field, messages_for_field in error.message_dict.items():
            parts.append(f"{field}: {' '.join(messages_for_field)}")
        return " ".join(parts)
    return " ".join(error.messages)


class SecretListView(RestrictedObjectListMixin, ObjectListView):
    queryset = Secret.objects.select_related("secret_group__organization", "secret_group__workspace", "secret_group__environment")
    table = tables.SecretTable
    filterset = filtersets.SecretFilterSet
    template_name = "automation/secret_list.html"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("secret_group__organization", "secret_group__workspace", "secret_group__environment")
            .order_by(
                "secret_group__organization__name",
                "secret_group__workspace__name",
                "secret_group__environment__name",
                "secret_group__name",
                "name",
            )
        )


class SecretDetailView(RestrictedObjectViewMixin, ObjectView):
    model = Secret
    template_name = "automation/secret_detail.html"

    def get_queryset(self):
        return super().get_queryset().select_related(
            "secret_group__organization",
            "secret_group__workspace",
            "secret_group__environment",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            context["secret_value"] = self.object.get_value()
            context["secret_value_error"] = ""
        except ValidationError as exc:
            if hasattr(exc, "message_dict"):
                error_message = " ".join(
                    " ".join(messages)
                    for messages in exc.message_dict.values()
                )
            else:
                error_message = " ".join(exc.messages)
            context["secret_value"] = ""
            context["secret_value_error"] = error_message

        return context


class SecretChangelogView(RestrictedObjectChangeLogMixin, ObjectChangeLogView):
    model = Secret
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


class SecretCreateView(RestrictedObjectEditMixin, ObjectEditView):
    model = Secret
    form_class = SecretForm
    success_message = "Secret created."


class SecretUpdateView(RestrictedObjectEditMixin, ObjectEditView):
    model = Secret
    form_class = SecretForm
    success_message = "Secret updated."


class SecretDeleteView(RestrictedObjectDeleteMixin, ObjectDeleteView):
    model = Secret
    success_message = "Secret deleted."


class SecretGroupListView(RestrictedObjectListMixin, ObjectListView):
    queryset = SecretGroup.objects.select_related("organization", "workspace", "environment")
    table = tables.SecretGroupTable
    filterset = filtersets.SecretGroupFilterSet
    template_name = "automation/secretgroup_list.html"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("organization", "workspace", "environment")
            .order_by("organization__name", "workspace__name", "environment__name", "name")
        )


class SecretGroupDetailView(RestrictedObjectViewMixin, ObjectView):
    model = SecretGroup
    template_name = "automation/secretgroup_detail.html"

    def get_queryset(self):
        secret_qs = Secret.objects.select_related(
            "secret_group__organization",
            "secret_group__workspace",
            "secret_group__environment",
        ).order_by("name")
        return (
            super()
            .get_queryset()
            .select_related("organization", "workspace", "environment")
            .prefetch_related(Prefetch("secrets", queryset=secret_qs))
            .annotate(secret_count=Count("secrets", distinct=True))
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["secret_rows"] = [{"secret": secret} for secret in self.object.secrets.all()]
        return context


class SecretGroupChangelogView(RestrictedObjectChangeLogMixin, ObjectChangeLogView):
    model = SecretGroup
    queryset = SecretGroup.objects.select_related("organization", "workspace", "environment").order_by(
        "organization__name",
        "workspace__name",
        "environment__name",
        "name",
    )


class SecretGroupCreateView(RestrictedObjectEditMixin, ObjectEditView):
    model = SecretGroup
    form_class = SecretGroupForm
    success_message = "Secret group created."


class SecretGroupUpdateView(RestrictedObjectEditMixin, ObjectEditView):
    model = SecretGroup
    form_class = SecretGroupForm
    success_message = "Secret group updated."


class SecretGroupDeleteView(RestrictedObjectDeleteMixin, ObjectDeleteView):
    model = SecretGroup
    success_message = "Secret group deleted."


def _build_run_display(run: WorkflowRun):
    return {
        "object": run,
        "input_json": _pretty_json(run.input_data),
        "output_json": _pretty_json(run.output_data),
        "context_json": _pretty_json(run.context_data),
        "steps_json": _pretty_json(run.step_results),
    }


def _build_form_validation_error(form) -> ValidationError:
    return ValidationError(
        {
            field: [str(error) for error in errors]
            for field, errors in form.errors.items()
        }
    )


def _parse_json_request_payload(request) -> dict:
    raw_body = request.body.decode("utf-8").strip()
    if not raw_body:
        return {}
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise ValidationError({"payload": "Request body must be valid JSON."}) from exc
    if not isinstance(payload, dict):
        raise ValidationError({"payload": "Request body must be a JSON object."})
    return payload


def _prepare_designer_execution(workflow, *, request) -> tuple[Workflow, dict]:
    payload = _parse_json_request_payload(request)
    if "definition" not in payload:
        raise ValidationError({"definition": "This field is required."})

    input_data = payload.get("input_data") or {}
    if not isinstance(input_data, dict):
        raise ValidationError({"input_data": "Input payload must be a JSON object."})

    form = WorkflowDesignerForm(
        data={"definition": json.dumps(payload["definition"])},
        instance=workflow,
    )
    if not form.is_valid():
        raise _build_form_validation_error(form)

    workflow = form.save()
    return workflow, input_data


def _is_node_primary_reachable(*, definition: dict, node_id: str) -> bool:
    nodes = definition.get("nodes", [])
    nodes_by_id = {node["id"]: node for node in nodes}
    if node_id not in nodes_by_id:
        return False

    trigger_node = next((node for node in nodes if node.get("kind") == "trigger"), None)
    if trigger_node is None:
        return False

    primary_edges, _auxiliary_edges = split_workflow_edges(definition.get("edges", []))
    adjacency: dict[str, list[str]] = {node["id"]: [] for node in nodes}
    for edge in primary_edges:
        adjacency.setdefault(edge["source"], []).append(edge["target"])

    visited: set[str] = set()
    stack = [trigger_node["id"]]
    while stack:
        current_node_id = stack.pop()
        if current_node_id in visited:
            continue
        if current_node_id == node_id:
            return True
        visited.add(current_node_id)
        stack.extend(adjacency.get(current_node_id, []))

    return False


def _build_designer_run_payload(run: WorkflowRun, *, mode: str, node: dict | None = None) -> dict:
    poll_url = reverse("workflow_designer_run_status", args=[run.workflow_id, run.pk])
    if run.status == WorkflowRun.StatusChoices.PENDING:
        message = "Workflow queued."
    elif run.status == WorkflowRun.StatusChoices.RUNNING:
        message = "Workflow running."
    elif run.status == WorkflowRun.StatusChoices.SUCCEEDED:
        message = "Workflow executed."
    else:
        message = run.error

    scheduler_state = run.scheduler_state if isinstance(run.scheduler_state, dict) else {}
    active_node_ids = scheduler_state.get("active_node_ids")
    failed_node_ids = scheduler_state.get("failed_node_ids")
    last_completed_node_id = None
    if run.step_results:
        last_step = run.step_results[-1]
        if isinstance(last_step, dict):
            last_completed_node_id = last_step.get("node_id")

    payload = {
        "mode": mode,
        "message": message,
        "poll_url": poll_url,
        "run": {
            "id": run.pk,
            "status": run.status,
            "badge_class": run.badge_class,
            "trigger_mode": run.trigger_mode,
            "step_count": run.step_count,
            "workflow_version": run.workflow_version.version,
            "error": run.error,
            "input_json": _pretty_json(run.input_data),
            "output_json": _pretty_json(run.output_data),
            "context_json": _pretty_json(run.context_data),
            "steps_json": _pretty_json(run.step_results),
            "active_node_ids": active_node_ids if isinstance(active_node_ids, list) else [],
            "failed_node_ids": failed_node_ids if isinstance(failed_node_ids, list) else [],
            "last_completed_node_id": (
                last_completed_node_id
                if isinstance(last_completed_node_id, str) and last_completed_node_id
                else None
            ),
        },
    }
    if node is not None:
        payload["node"] = {
            "id": node.get("id"),
            "label": node.get("label") or node.get("id"),
            "kind": node.get("kind"),
            "type": node.get("type"),
        }
    return payload


def _get_workflow_connection_queryset(workflow):
    base_queryset = WorkflowConnection.objects.select_related(
        "organization",
        "workspace",
        "environment",
        "credential_secret",
    ).filter(organization=workflow.organization, enabled=True)

    if workflow.environment_id:
        return base_queryset.filter(
            Q(environment=workflow.environment)
            | Q(environment__isnull=True, workspace=workflow.workspace)
            | Q(environment__isnull=True, workspace__isnull=True, organization=workflow.organization)
        ).order_by("integration_id", "name")

    if workflow.workspace_id:
        return base_queryset.filter(
            Q(workspace=workflow.workspace, environment__isnull=True)
            | Q(workspace__isnull=True, environment__isnull=True, organization=workflow.organization)
        ).order_by("integration_id", "name")

    return base_queryset.filter(
        workspace__isnull=True,
        environment__isnull=True,
    ).order_by("integration_id", "name")


def _serialize_workflow_connections_for_designer(workflow) -> list[dict]:
    return [
        {
            "connection_type": connection.connection_type,
            "enabled": connection.enabled,
            "id": connection.pk,
            "integration_id": connection.integration_id,
            "label": (
                f"{connection.name} ({connection.scope_label})"
                if connection.scope_label
                else connection.name
            ),
            "name": connection.name,
            "scope_label": connection.scope_label,
        }
        for connection in _get_workflow_connection_queryset(workflow)
    ]


class WorkflowListView(RestrictedObjectListMixin, ObjectListView):
    queryset = Workflow.objects.select_related("organization", "workspace", "environment")
    table = tables.WorkflowTable
    filterset = filtersets.WorkflowFilterSet
    template_name = "automation/workflow_list.html"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("organization", "workspace", "environment")
            .order_by("organization__name", "workspace__name", "environment__name", "name")
        )


class WorkflowConnectionListView(RestrictedObjectListMixin, ObjectListView):
    queryset = WorkflowConnection.objects.select_related(
        "organization",
        "workspace",
        "environment",
        "credential_secret",
        "credential_secret__secret_group",
    )
    table = tables.WorkflowConnectionTable
    filterset = filtersets.WorkflowConnectionFilterSet
    template_name = "automation/workflowconnection_list.html"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "organization",
                "workspace",
                "environment",
                "credential_secret",
                "credential_secret__secret_group",
            )
            .order_by("organization__name", "workspace__name", "environment__name", "integration_id", "name")
        )


class WorkflowConnectionDetailView(RestrictedObjectViewMixin, ObjectView):
    model = WorkflowConnection
    template_name = "automation/workflowconnection_detail.html"

    def get_queryset(self):
        return super().get_queryset().select_related(
            "organization",
            "workspace",
            "environment",
            "credential_secret",
            "credential_secret__secret_group",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        connection_definition = get_catalog_connection_type(self.object.connection_type)
        context["connection_definition"] = connection_definition
        context["auth_config_json"] = _pretty_json(self.object.auth_config)
        context["metadata_json"] = _pretty_json(self.object.metadata)
        return context


class WorkflowConnectionChangelogView(RestrictedObjectChangeLogMixin, ObjectChangeLogView):
    model = WorkflowConnection
    queryset = WorkflowConnection.objects.select_related(
        "organization",
        "workspace",
        "environment",
        "credential_secret",
        "credential_secret__secret_group",
    ).order_by(
        "organization__name",
        "workspace__name",
        "environment__name",
        "integration_id",
        "name",
    )


class WorkflowConnectionCreateView(RestrictedObjectEditMixin, ObjectEditView):
    model = WorkflowConnection
    form_class = WorkflowConnectionForm
    success_message = "Workflow connection created."


class WorkflowConnectionUpdateView(RestrictedObjectEditMixin, ObjectEditView):
    model = WorkflowConnection
    form_class = WorkflowConnectionForm
    success_message = "Workflow connection updated."


class WorkflowConnectionDeleteView(RestrictedObjectDeleteMixin, ObjectDeleteView):
    model = WorkflowConnection
    success_message = "Workflow connection deleted."


class WorkflowDetailView(RestrictedObjectViewMixin, ObjectView):
    model = Workflow
    template_name = "automation/workflow_detail.html"

    def get_queryset(self):
        return super().get_queryset().select_related("organization", "workspace", "environment")

    def get_context_data(self, **kwargs):
        run_form = kwargs.pop("run_form", None) or WorkflowRunForm(initial={"input_data": {}})
        context = super().get_context_data(**kwargs)
        normalized_definition = normalize_workflow_definition_nodes(self.object.definition)
        recent_runs = list(self.object.runs.order_by("-created")[:5])
        context["show_side_panel"] = True
        context["can_design"] = context["can_edit"] and workflow_definition_supports_catalog_designer(
            normalized_definition
        )
        context["can_execute"] = context["can_edit"]
        context["workflow_nodes"] = normalized_definition.get("nodes", [])
        context["workflow_edges"] = normalized_definition.get("edges", [])
        context["workflow_designer_url"] = reverse("workflow_designer", args=[self.object.pk])
        context["workflow_connections"] = _serialize_workflow_connections_for_designer(self.object)
        context["workflow_connection_list_url"] = reverse("workflowconnection_list")
        context["workflow_connection_add_url"] = (
            f'{reverse("workflowconnection_add")}?environment={self.object.environment_id}'
            if self.object.environment_id
            else reverse("workflowconnection_add")
        )
        context["run_form"] = run_form
        context["latest_run"] = _build_run_display(recent_runs[0]) if recent_runs else None
        context["recent_runs"] = [_build_run_display(run) for run in recent_runs]
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        assert_object_action_allowed(
            self.object,
            request=request,
            action="change",
        )
        run_form = WorkflowRunForm(request.POST)
        if not run_form.is_valid():
            context = self.get_context_data(object=self.object, run_form=run_form)
            return self.render_to_response(context)

        try:
            run = enqueue_workflow(
                self.object,
                input_data=run_form.cleaned_data.get("input_data") or {},
                actor=request.user,
            )
        except ValidationError as exc:
            messages.error(request, _flatten_validation_error(exc))
            context = self.get_context_data(object=self.object, run_form=run_form)
            return self.render_to_response(context)

        messages.success(request, f"Workflow run #{run.pk} queued.")
        return redirect(self.object.get_absolute_url())


class WorkflowChangelogView(RestrictedObjectChangeLogMixin, ObjectChangeLogView):
    model = Workflow
    queryset = Workflow.objects.select_related("organization", "workspace", "environment").order_by(
        "organization__name",
        "workspace__name",
        "environment__name",
        "name",
    )


class WorkflowCreateView(RestrictedObjectEditMixin, ObjectEditView):
    model = Workflow
    form_class = WorkflowForm
    success_message = "Workflow created."


class WorkflowUpdateView(RestrictedObjectEditMixin, ObjectEditView):
    model = Workflow
    form_class = WorkflowForm
    success_message = "Workflow updated."


class WorkflowDesignerView(RestrictedObjectEditMixin, ObjectEditView):
    model = Workflow
    form_class = WorkflowDesignerForm
    template_name = "automation/workflow_designer.html"
    success_message = "Workflow designer updated."
    submit_label = "Save workflow"

    def get_page_title(self):
        return f"Designer: {self.object}"

    def get_return_url(self, request, obj=None):
        workflow = obj or self.object
        return reverse("workflow_designer", args=[workflow.pk])

    def get(self, request, *args, **kwargs):
        normalized_definition = normalize_workflow_definition_nodes(self.object.definition)
        if not workflow_definition_supports_catalog_designer(normalized_definition):
            messages.error(request, WORKFLOW_DESIGNER_CATALOG_ONLY_MESSAGE)
            return redirect(self.object.get_absolute_url())
        form = self.get_form()
        return render(request, self.template_name, self.get_context_data(request, form))

    def get_context_data(self, request, form):
        context = super().get_context_data(request, form)
        normalized_definition = normalize_workflow_definition_nodes(self.object.definition)
        context.update(
            {
                "can_execute": True,
                "run_form": WorkflowRunForm(initial={"input_data": {}}),
                "workflow_definition": normalized_definition,
                "workflow_catalog": build_workflow_catalog_payload(),
                "workflow_connections": _serialize_workflow_connections_for_designer(self.object),
                "workflow_nodes": normalized_definition.get("nodes", []),
                "workflow_list_url": reverse("workflow_list"),
                "workflow_detail_url": self.object.get_absolute_url(),
                "workflow_edit_url": reverse("workflow_edit", args=[self.object.pk]),
                "workflow_changelog_url": reverse("workflow_changelog", args=[self.object.pk]),
                "workflow_designer_run_url": reverse("workflow_designer_run", args=[self.object.pk]),
                "workflow_designer_node_run_url_template": reverse(
                    "workflow_designer_node_run",
                    args=[self.object.pk, "__node_id__"],
                ),
            }
        )
        return context


class WorkflowDesignerRunView(View):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        workflow = (
            Workflow.objects.select_related("organization", "workspace", "environment")
            .filter(pk=kwargs["pk"])
            .first()
        )
        if workflow is None:
            return JsonResponse({"detail": "Workflow not found."}, status=404)

        assert_object_action_allowed(workflow, request=request, action="change")
        try:
            workflow, input_data = _prepare_designer_execution(workflow, request=request)
        except ValidationError as exc:
            return JsonResponse({"detail": _flatten_validation_error(exc)}, status=400)

        try:
            run = enqueue_workflow(
                workflow,
                input_data=input_data,
                actor=request.user,
            )
        except ValidationError as exc:
            return JsonResponse({"detail": _flatten_validation_error(exc)}, status=400)

        return JsonResponse(_build_designer_run_payload(run, mode="workflow"), status=202)


class WorkflowDesignerNodeRunView(View):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        workflow = (
            Workflow.objects.select_related("organization", "workspace", "environment")
            .filter(pk=kwargs["pk"])
            .first()
        )
        if workflow is None:
            return JsonResponse({"detail": "Workflow not found."}, status=404)

        assert_object_action_allowed(workflow, request=request, action="change")
        try:
            workflow, input_data = _prepare_designer_execution(workflow, request=request)
        except ValidationError as exc:
            return JsonResponse({"detail": _flatten_validation_error(exc)}, status=400)

        definition = normalize_workflow_definition_nodes(workflow.definition or {})
        nodes_by_id = {node["id"]: node for node in definition.get("nodes", [])}
        node = nodes_by_id.get(kwargs["node_id"])
        if node is None:
            return JsonResponse({"detail": f'Workflow does not define node "{kwargs["node_id"]}".'}, status=400)

        try:
            run = enqueue_workflow(
                workflow,
                input_data=input_data,
                trigger_mode="manual:node",
                actor=request.user,
                execution_mode=WorkflowRun.ExecutionModeChoices.NODE_PREVIEW,
                target_node_id=node["id"],
            )
            mode = "node_preview"
        except ValidationError as exc:
            return JsonResponse({"detail": _flatten_validation_error(exc)}, status=400)

        return JsonResponse(_build_designer_run_payload(run, mode=mode, node=node), status=202)


class WorkflowDesignerRunStatusView(View):
    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        workflow = (
            Workflow.objects.select_related("organization", "workspace", "environment")
            .filter(pk=kwargs["pk"])
            .first()
        )
        if workflow is None:
            return JsonResponse({"detail": "Workflow not found."}, status=404)

        assert_object_action_allowed(workflow, request=request, action="view")
        run = (
            WorkflowRun.objects.select_related("workflow", "workflow_version")
            .filter(pk=kwargs["run_id"], workflow=workflow)
            .first()
        )
        if run is None:
            return JsonResponse({"detail": "Workflow run not found."}, status=404)

        node = None
        if run.target_node_id:
            definition = normalize_workflow_definition_nodes(run.workflow_version.definition or {})
            nodes_by_id = {item["id"]: item for item in definition.get("nodes", [])}
            node = nodes_by_id.get(run.target_node_id)

        return JsonResponse(
            _build_designer_run_payload(
                run,
                mode=run.execution_mode,
                node=node,
            )
        )


class WorkflowDeleteView(RestrictedObjectDeleteMixin, ObjectDeleteView):
    model = Workflow
    template_name = "automation/workflow_delete.html"
    success_message = "Workflow deleted."

    def get_extra_context(self, request, obj):
        run_count = obj.runs.count()
        version_count = obj.versions.count()
        step_run_count = WorkflowStepRun.objects.filter(run__workflow=obj).count()
        return {
            "workflow_run_count": run_count,
            "workflow_version_count": version_count,
            "workflow_step_run_count": step_run_count,
            "has_workflow_history": bool(run_count or version_count or step_run_count),
        }

    def post(self, request, *args, **kwargs):
        delete_history = request.POST.get("delete_history") in {"1", "true", "True", "on"}
        if not delete_history:
            return super().post(request, *args, **kwargs)

        success_message = self.get_success_message(self.object)
        return_url = self.get_return_url(request, self.object)
        with transaction.atomic():
            WorkflowRun.objects.filter(workflow=self.object).delete()
            WorkflowVersion.objects.filter(workflow=self.object).delete()
            self.object.delete()

        if success_message:
            messages.success(request, success_message)
        return redirect(return_url)


@method_decorator(csrf_exempt, name="dispatch")
class WorkflowWebhookTriggerView(View):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        workflow = (
            Workflow.objects.select_related("organization", "workspace", "environment")
            .filter(pk=kwargs["pk"], enabled=True)
            .first()
        )
        if workflow is None:
            return JsonResponse({"detail": "Workflow not found."}, status=404)

        nodes = normalize_workflow_definition_nodes(workflow.definition or {}).get("nodes", [])
        trigger_node = next((node for node in nodes if node.get("kind") == "trigger"), None)
        if trigger_node is None:
            return JsonResponse({"detail": "Workflow has no trigger node."}, status=400)

        try:
            trigger_mode, input_data, trigger_metadata = prepare_catalog_webhook_request(
                workflow=workflow,
                node=trigger_node,
                request=request,
            )
        except ValidationError as exc:
            message = " ".join(exc.messages)
            return JsonResponse({"detail": message}, status=400)

        run = execute_workflow(
            workflow,
            input_data=input_data,
            trigger_mode=trigger_mode,
            trigger_metadata=trigger_metadata,
            actor=None,
        )
        status_code = 200 if run.status == WorkflowRun.StatusChoices.SUCCEEDED else 400
        return JsonResponse(
            {
                "run_id": run.pk,
                "status": run.status,
                "error": run.error,
                "output_data": run.output_data,
            },
            status=status_code,
        )
