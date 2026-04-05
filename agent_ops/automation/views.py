import base64
import hashlib
import json
import secrets
import time
from datetime import datetime, timezone as datetime_timezone
from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.http import Http404, JsonResponse
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
from automation.integrations.openai.app import (
    OPENAI_AUTH_USER_AGENT,
    OPENAI_CODEX_OAUTH_CLIENT_ID,
    OPENAI_DEVICE_AUTH_CALLBACK_URL,
    OPENAI_DEVICE_AUTH_TOKEN_URL,
    OPENAI_DEVICE_AUTH_USERCODE_URL,
    OPENAI_DEVICE_AUTH_VERIFICATION_URL,
    OPENAI_OAUTH_TOKEN_URL,
)
from automation.models import Secret, SecretGroup, Workflow, WorkflowConnection, WorkflowConnectionState, WorkflowRun, WorkflowStepRun, WorkflowVersion
from automation.primitives import canonicalize_workflow_definition, normalize_workflow_definition_nodes
from automation.runtime import enqueue_workflow, execute_workflow
from automation.tools.base import _http_json_request
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
from users.restrictions import assert_object_action_allowed, restrict_queryset


WORKFLOW_CONNECTION_OPENAI_OAUTH_SESSION_PREFIX = "workflow_connection_openai_oauth"


def _openai_auth_headers() -> dict[str, str]:
    return {
        "Accept": "application/json",
        "User-Agent": OPENAI_AUTH_USER_AGENT,
    }


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


def _workflow_connection_popup_requested(request) -> bool:
    return (request.GET.get("popup") or request.POST.get("popup")) == "1"


def _workflow_connection_return_url(request) -> str | None:
    raw_value = request.POST.get("return_url") or request.GET.get("return_url")
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None
    return raw_value.strip()


def _build_workflow_connection_url(url_name: str, connection: WorkflowConnection, *, popup: bool, return_url: str | None) -> str:
    url = reverse(url_name, args=[connection.pk])
    query_params: dict[str, str] = {}
    if popup:
        query_params["popup"] = "1"
    if return_url:
        query_params["return_url"] = return_url
    if query_params:
        return f"{url}?{urlencode(query_params)}"
    return url


def _connection_field_value(connection: WorkflowConnection, field_key: str, default: str | None = None) -> str | None:
    raw_value = (connection.field_values or {}).get(field_key)
    if isinstance(raw_value, str) and raw_value.strip():
        return raw_value.strip()
    return default


def _connection_secret_value(connection: WorkflowConnection, field_key: str) -> str | None:
    raw_value = (connection.field_values or {}).get(field_key)
    if not isinstance(raw_value, dict) or connection.secret_group is None:
        return None
    secret_name = raw_value.get("secret_name")
    if not isinstance(secret_name, str) or not secret_name.strip():
        return None
    secret = connection.secret_group.get_secret(name=secret_name.strip())
    if secret is None or not secret.enabled:
        return None
    try:
        resolved = secret.get_value(obj=connection)
    except ValidationError:
        return None
    if not isinstance(resolved, str) or not resolved.strip():
        return None
    return resolved.strip()


def _connection_supports_oauth(connection: WorkflowConnection) -> bool:
    connection_definition = get_catalog_connection_type(connection.connection_type)
    return bool(connection_definition and connection_definition.oauth2)


def _connection_oauth_is_connected(connection: WorkflowConnection) -> bool:
    state = getattr(connection, "state", None)
    if state is None:
        return False
    refresh_token = (state.state_values or {}).get("refresh_token")
    return isinstance(refresh_token, str) and bool(refresh_token.strip())


def _serialize_workflow_connection_for_designer(connection: WorkflowConnection) -> dict:
    supports_oauth = _connection_supports_oauth(connection)
    oauth_connected = _connection_oauth_is_connected(connection)
    return {
        "connection_type": connection.connection_type,
        "edit_url": reverse("workflowconnection_edit", args=[connection.pk]),
        "enabled": connection.enabled,
        "id": connection.pk,
        "integration_id": connection.integration_id,
        "label": (
            f"{connection.name} ({connection.scope_label})"
            if connection.scope_label
            else connection.name
        ),
        "name": connection.name,
        "oauth_connect_url": reverse("workflowconnection_openai_oauth_start", args=[connection.pk]) if supports_oauth else "",
        "oauth_connected": oauth_connected,
        "scope_label": connection.scope_label,
        "supports_oauth": supports_oauth,
    }


def _build_workflow_connection_popup_response(request, connection: WorkflowConnection, *, action: str) -> JsonResponse:
    popup_complete_url = _build_workflow_connection_url(
        "workflowconnection_popup_complete",
        connection,
        popup=True,
        return_url=_workflow_connection_return_url(request),
    )
    popup_complete_url = f"{popup_complete_url}&action={action}" if "?" in popup_complete_url else f"{popup_complete_url}?action={action}"
    return redirect(popup_complete_url)


def _build_workflow_connection_oauth_session_key(state_token: str) -> str:
    return f"{WORKFLOW_CONNECTION_OPENAI_OAUTH_SESSION_PREFIX}:{state_token}"


def _generate_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def _resolve_openai_oauth_client_id(connection: WorkflowConnection) -> str:
    return _connection_field_value(connection, "oauth_client_id", default=OPENAI_CODEX_OAUTH_CLIENT_ID) or OPENAI_CODEX_OAUTH_CLIENT_ID


def _decode_jwt_payload(token: str) -> dict | None:
    if not isinstance(token, str) or not token.strip():
        return None
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8")
        parsed = json.loads(decoded)
    except (ValueError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _extract_openai_account_id(*tokens: str | None) -> str | None:
    for token in tokens:
        payload = _decode_jwt_payload(token or "")
        if not payload:
            continue
        claim = payload.get("https://api.openai.com/auth")
        if isinstance(claim, dict):
            account_id = claim.get("chatgpt_account_id")
            if isinstance(account_id, str) and account_id.strip():
                return account_id.strip()
        account_id = payload.get("chatgpt_account_id")
        if isinstance(account_id, str) and account_id.strip():
            return account_id.strip()
        organizations = payload.get("organizations")
        if isinstance(organizations, list):
            for organization in organizations:
                if isinstance(organization, dict):
                    organization_id = organization.get("id")
                    if isinstance(organization_id, str) and organization_id.strip():
                        return organization_id.strip()
    return None


def _exchange_openai_device_authorization_code(
    *,
    client_id: str,
    token_url: str,
    authorization_code: str,
    code_verifier: str,
    client_secret: str | None = None,
) -> dict[str, object]:
    exchange_payload = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "code": authorization_code,
        "code_verifier": code_verifier,
        "redirect_uri": OPENAI_DEVICE_AUTH_CALLBACK_URL,
    }
    if client_secret:
        exchange_payload["client_secret"] = client_secret
    exchange_response, _ = _http_json_request(
        method="POST",
        url=token_url,
        headers=_openai_auth_headers(),
        form_body=exchange_payload,
    )
    if not isinstance(exchange_response, dict):
        raise ValidationError({"definition": "OpenAI device-login token exchange returned an unexpected response."})
    access_token = exchange_response.get("access_token")
    refresh_token = exchange_response.get("refresh_token")
    if (
        not isinstance(access_token, str)
        or not access_token.strip()
        or not isinstance(refresh_token, str)
        or not refresh_token.strip()
    ):
        raise ValidationError({"definition": "OpenAI device-login token exchange did not return the required tokens."})
    return exchange_response


def _parse_openai_device_auth_expiry(raw_value) -> int | None:
    if isinstance(raw_value, str) and raw_value.strip():
        try:
            return int(datetime.fromisoformat(raw_value.strip()).timestamp())
        except ValueError:
            return None
    if raw_value not in (None, ""):
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return None
    return None


def _get_allowed_workflow_connection(request, *, pk: int, action: str = "change") -> WorkflowConnection:
    queryset = restrict_queryset(
        WorkflowConnection.objects.select_related(
            "organization",
            "workspace",
            "environment",
            "secret_group",
            "state",
        ),
        request=request,
        action=action,
    )
    connection = queryset.filter(pk=pk).first()
    if connection is None:
        raise Http404("Workflow connection not found.")
    assert_object_action_allowed(connection, request=request, action=action)
    return connection


def _build_openai_oauth_context(request, connection: WorkflowConnection | None) -> dict:
    popup = _workflow_connection_popup_requested(request)
    return_url = _workflow_connection_return_url(request)
    if connection is None or connection.connection_type != "openai.api":
        return {
            "available": False,
            "verification_url": OPENAI_DEVICE_AUTH_VERIFICATION_URL,
        }

    auth_mode = _connection_field_value(connection, "auth_mode", default="api_key")
    client_id = _resolve_openai_oauth_client_id(connection)
    state = getattr(connection, "state", None)
    state_values = state.state_values if state is not None else {}
    refresh_token = state_values.get("refresh_token")
    account_id = state_values.get("account_id")
    connected = isinstance(refresh_token, str) and bool(refresh_token.strip())
    can_start = bool(connection.pk and auth_mode == "oauth2_authorization_code" and client_id)

    return {
        "account_id": account_id if isinstance(account_id, str) and account_id.strip() else None,
        "auth_mode": auth_mode,
        "available": True,
        "can_start": can_start,
        "client_id": client_id,
        "connected": connected,
        "popup": popup,
        "start_url": _build_workflow_connection_url(
            "workflowconnection_openai_oauth_start",
            connection,
            popup=popup,
            return_url=return_url,
        ) if can_start else None,
        "verification_url": OPENAI_DEVICE_AUTH_VERIFICATION_URL,
        "status_label": "Connected" if connected else "Authorization required",
    }


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
    skipped_node_ids = scheduler_state.get("skipped_node_ids")
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
            "skipped_node_ids": skipped_node_ids if isinstance(skipped_node_ids, list) else [],
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
        "secret_group",
        "state",
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
    return [_serialize_workflow_connection_for_designer(connection) for connection in _get_workflow_connection_queryset(workflow)]


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
        "secret_group",
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
                "secret_group",
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
            "secret_group",
            "state",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        connection_definition = get_catalog_connection_type(self.object.connection_type)
        context["connection_definition"] = connection_definition
        context["field_values_json"] = _pretty_json(self.object.field_values)
        context["state_summary_json"] = _pretty_json(getattr(getattr(self.object, "state", None), "summary", None))
        context["metadata_json"] = _pretty_json(self.object.metadata)
        context["workflow_connection_oauth"] = _build_openai_oauth_context(self.request, self.object)
        return context


class WorkflowConnectionChangelogView(RestrictedObjectChangeLogMixin, ObjectChangeLogView):
    model = WorkflowConnection
    queryset = WorkflowConnection.objects.select_related(
        "organization",
        "workspace",
        "environment",
        "secret_group",
        "state",
    ).order_by(
        "organization__name",
        "workspace__name",
        "environment__name",
        "integration_id",
        "name",
    )


class WorkflowConnectionEditViewMixin:
    template_name = "automation/workflowconnection_form.html"

    def get_context_data(self, request, form):
        context = super().get_context_data(request, form)
        connection = self.object if getattr(self.object, "pk", None) else None
        context["workflow_connection_popup"] = _workflow_connection_popup_requested(request)
        context["workflow_connection_oauth"] = _build_openai_oauth_context(request, connection)
        return context

    def post(self, request, *args, **kwargs):
        form = self.get_form(data=request.POST, files=request.FILES)
        if form.is_valid():
            created = self.object.pk is None
            self.object = self.form_save(form)
            success_message = self.get_success_message(self.object, created)
            if success_message:
                messages.success(request, success_message)

            if _workflow_connection_popup_requested(request):
                return _build_workflow_connection_popup_response(request, self.object, action="saved")

            return redirect(self.get_return_url(request, self.object))

        return render(request, self.template_name, self.get_context_data(request, form))


class WorkflowConnectionCreateView(RestrictedObjectEditMixin, WorkflowConnectionEditViewMixin, ObjectEditView):
    model = WorkflowConnection
    form_class = WorkflowConnectionForm
    success_message = "Workflow connection created."


class WorkflowConnectionUpdateView(RestrictedObjectEditMixin, WorkflowConnectionEditViewMixin, ObjectEditView):
    model = WorkflowConnection
    form_class = WorkflowConnectionForm
    success_message = "Workflow connection updated."


class WorkflowConnectionPopupCompleteView(RestrictedObjectViewMixin, ObjectView):
    model = WorkflowConnection
    template_name = "automation/workflowconnection_popup_complete.html"

    def get_queryset(self):
        return super().get_queryset().select_related(
            "organization",
            "workspace",
            "environment",
            "secret_group",
            "state",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["popup_action"] = self.request.GET.get("action") or "saved"
        context["popup_return_url"] = _workflow_connection_return_url(self.request)
        return context


class WorkflowConnectionOpenAIOAuthStartView(View):
    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        connection = _get_allowed_workflow_connection(request, pk=kwargs["pk"], action="change")
        if connection.connection_type != "openai.api":
            messages.error(request, "This connection type does not support the OpenAI OAuth flow.")
            return redirect(connection.get_absolute_url())

        auth_mode = _connection_field_value(connection, "auth_mode", default="api_key")
        if auth_mode != "oauth2_authorization_code":
            messages.error(request, "Switch this connection to OAuth mode before connecting an account.")
            return redirect(
                _build_workflow_connection_url(
                    "workflowconnection_edit",
                    connection,
                    popup=_workflow_connection_popup_requested(request),
                    return_url=_workflow_connection_return_url(request),
                )
            )

        client_id = _resolve_openai_oauth_client_id(connection)
        # Codex device auth works with the minimal client_id payload.
        # Avoid undocumented extras here because Cloudflare/OpenAI routing is
        # stricter than the browser login flow and can fail unexpectedly.
        start_payload = {"client_id": client_id}
        try:
            response_body, _ = _http_json_request(
                method="POST",
                url=OPENAI_DEVICE_AUTH_USERCODE_URL,
                headers=_openai_auth_headers(),
                json_body=start_payload,
            )
        except ValidationError as exc:
            messages.error(request, _flatten_validation_error(exc))
            return redirect(
                _build_workflow_connection_url(
                    "workflowconnection_edit",
                    connection,
                    popup=_workflow_connection_popup_requested(request),
                    return_url=_workflow_connection_return_url(request),
                )
            )

        if not isinstance(response_body, dict):
            messages.error(request, "OpenAI device login returned an unexpected response.")
            return redirect(
                _build_workflow_connection_url(
                    "workflowconnection_edit",
                    connection,
                    popup=_workflow_connection_popup_requested(request),
                    return_url=_workflow_connection_return_url(request),
                )
            )

        device_auth_id = response_body.get("device_auth_id")
        user_code = response_body.get("user_code")
        if not isinstance(device_auth_id, str) or not device_auth_id.strip() or not isinstance(user_code, str) or not user_code.strip():
            messages.error(request, "OpenAI device login did not return a device code.")
            return redirect(
                _build_workflow_connection_url(
                    "workflowconnection_edit",
                    connection,
                    popup=_workflow_connection_popup_requested(request),
                    return_url=_workflow_connection_return_url(request),
                )
            )

        session_token = secrets.token_urlsafe(24)
        expires_at = _parse_openai_device_auth_expiry(response_body.get("expires_at"))
        interval_value = response_body.get("interval")
        try:
            poll_interval_seconds = max(1, int(interval_value))
        except (TypeError, ValueError):
            poll_interval_seconds = 5
        request.session[_build_workflow_connection_oauth_session_key(session_token)] = {
            "client_id": client_id,
            "connection_id": connection.pk,
            "device_auth_id": device_auth_id.strip(),
            "expires_at": expires_at,
            "popup": _workflow_connection_popup_requested(request),
            "poll_interval_seconds": poll_interval_seconds,
            "return_url": _workflow_connection_return_url(request),
            "user_code": user_code.strip(),
        }
        request.session.modified = True

        context = {
            "connection": connection,
            "expires_at": datetime.fromtimestamp(expires_at, tz=datetime_timezone.utc) if expires_at else None,
            "poll_interval_ms": poll_interval_seconds * 1000,
            "poll_url": reverse("workflowconnection_openai_oauth_poll", args=[session_token]),
            "verification_url": OPENAI_DEVICE_AUTH_VERIFICATION_URL,
            "workflow_connection_popup": _workflow_connection_popup_requested(request),
            "workflow_connection_return_url": _workflow_connection_return_url(request),
            "user_code": user_code.strip(),
        }
        return render(request, "automation/workflowconnection_openai_device_authorize.html", context)


class WorkflowConnectionOpenAIOAuthPollView(View):
    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        session_key = _build_workflow_connection_oauth_session_key(kwargs["session_token"])
        session_data = request.session.get(session_key)
        if not isinstance(session_data, dict):
            return JsonResponse({"message": "Authorization session expired.", "status": "expired"}, status=410)

        expires_at = session_data.get("expires_at")
        try:
            expired = int(expires_at) <= int(time.time())
        except (TypeError, ValueError):
            expired = False
        if expired:
            request.session.pop(session_key, None)
            request.session.modified = True
            return JsonResponse({"message": "Authorization session expired.", "status": "expired"}, status=410)

        connection = _get_allowed_workflow_connection(request, pk=int(session_data["connection_id"]), action="change")
        popup = bool(session_data.get("popup"))
        return_url = session_data.get("return_url") if isinstance(session_data.get("return_url"), str) else None
        edit_url = _build_workflow_connection_url(
            "workflowconnection_edit",
            connection,
            popup=popup,
            return_url=return_url,
        )
        poll_payload = {
            "device_auth_id": str(session_data.get("device_auth_id") or ""),
            "user_code": str(session_data.get("user_code") or ""),
        }

        try:
            response_body, _ = _http_json_request(
                method="POST",
                url=OPENAI_DEVICE_AUTH_TOKEN_URL,
                headers=_openai_auth_headers(),
                json_body=poll_payload,
            )
        except ValidationError as exc:
            message = _flatten_validation_error(exc)
            lowered = message.lower()
            if (
                "failed with 403" in lowered
                or "failed with 404" in lowered
                or "authorization_pending" in lowered
                or '"pending"' in lowered
                or "not yet authorized" in lowered
            ):
                return JsonResponse({"message": "Waiting for authorization.", "status": "pending"})
            if "slow_down" in lowered:
                return JsonResponse({"message": "OpenAI asked to slow down polling.", "status": "pending"})
            if "expired" in lowered:
                request.session.pop(session_key, None)
                request.session.modified = True
                return JsonResponse({"message": "Authorization session expired.", "status": "expired"}, status=410)
            return JsonResponse({"message": message, "status": "error"}, status=502)

        if not isinstance(response_body, dict):
            return JsonResponse({"message": "OpenAI device login returned an unexpected response.", "status": "error"}, status=502)

        oauth_error = response_body.get("error")
        if isinstance(oauth_error, str) and oauth_error.strip():
            lowered = oauth_error.strip().lower()
            if lowered in {"authorization_pending", "pending", "slow_down"}:
                return JsonResponse({"message": "Waiting for authorization.", "status": "pending"})
            if "expired" in lowered:
                request.session.pop(session_key, None)
                request.session.modified = True
                return JsonResponse({"message": "Authorization session expired.", "status": "expired"}, status=410)
            return JsonResponse({"message": oauth_error.strip(), "status": "error"}, status=502)

        authorization_code = response_body.get("authorization_code")
        code_verifier = response_body.get("code_verifier")
        if (
            not isinstance(authorization_code, str)
            or not authorization_code.strip()
            or not isinstance(code_verifier, str)
            or not code_verifier.strip()
        ):
            return JsonResponse(
                {"message": "OpenAI device login did not return an authorization code.", "status": "error"},
                status=502,
            )

        client_secret = _connection_secret_value(connection, "oauth_client_secret")
        token_url = _connection_field_value(connection, "oauth_token_url", default=OPENAI_OAUTH_TOKEN_URL) or OPENAI_OAUTH_TOKEN_URL
        try:
            token_response = _exchange_openai_device_authorization_code(
                client_id=str(session_data.get("client_id") or _resolve_openai_oauth_client_id(connection)),
                token_url=token_url,
                authorization_code=authorization_code.strip(),
                code_verifier=code_verifier.strip(),
                client_secret=client_secret,
            )
        except ValidationError as exc:
            return JsonResponse({"message": _flatten_validation_error(exc), "status": "error"}, status=502)

        access_token = str(token_response.get("access_token") or "").strip()
        refresh_token = str(token_response.get("refresh_token") or "").strip()
        expires_in = token_response.get("expires_in")
        id_token = token_response.get("id_token") if isinstance(token_response.get("id_token"), str) else None
        connection_state = getattr(connection, "state", None)
        if connection_state is None:
            connection_state, _ = WorkflowConnectionState.objects.get_or_create(connection=connection)
            connection.state = connection_state
        state_values = connection_state.state_values or {}
        state_values["access_token"] = access_token
        state_values["refresh_token"] = refresh_token
        if expires_in not in (None, ""):
            try:
                state_values["expires_at"] = int(time.time()) + int(expires_in)
            except (TypeError, ValueError):
                state_values.pop("expires_at", None)
        account_id = _extract_openai_account_id(
            id_token,
            access_token,
        )
        if account_id:
            state_values["account_id"] = account_id
        connection_state.state_values = state_values
        connection_state.mark_refreshed()
        connection_state.full_clean()
        connection_state.save()

        request.session.pop(session_key, None)
        request.session.modified = True
        messages.success(request, f'Connected OpenAI account for "{connection.name}".')
        redirect_url = (
            _build_workflow_connection_url(
                "workflowconnection_popup_complete",
                connection,
                popup=True,
                return_url=return_url,
            ) + "&action=oauth_connected"
            if popup
            else edit_url
        )
        return JsonResponse({"redirect_url": redirect_url, "status": "authorized"})


class WorkflowConnectionOpenAIOAuthCallbackView(View):
    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        state_token = request.GET.get("state")
        if not isinstance(state_token, str) or not state_token.strip():
            messages.error(request, "Missing OAuth state.")
            return redirect(reverse("workflowconnection_list"))

        session_key = _build_workflow_connection_oauth_session_key(state_token.strip())
        session_data = request.session.pop(session_key, None)
        request.session.modified = True
        if not isinstance(session_data, dict):
            messages.error(request, "OAuth session expired. Start the connection flow again.")
            return redirect(reverse("workflowconnection_list"))

        connection = _get_allowed_workflow_connection(request, pk=int(session_data["connection_id"]), action="change")
        popup = bool(session_data.get("popup"))
        return_url = session_data.get("return_url") if isinstance(session_data.get("return_url"), str) else None
        edit_url = _build_workflow_connection_url(
            "workflowconnection_edit",
            connection,
            popup=popup,
            return_url=return_url,
        )

        oauth_error = request.GET.get("error")
        if isinstance(oauth_error, str) and oauth_error.strip():
            messages.error(request, f"OpenAI OAuth failed: {oauth_error.strip()}")
            return redirect(edit_url)

        code = request.GET.get("code")
        if not isinstance(code, str) or not code.strip():
            messages.error(request, "OpenAI OAuth did not return an authorization code.")
            return redirect(edit_url)

        client_id = _resolve_openai_oauth_client_id(connection)
        token_url = _connection_field_value(connection, "oauth_token_url", default=OPENAI_OAUTH_TOKEN_URL)
        if not client_id or not token_url:
            messages.error(request, "Connection is missing OAuth client settings.")
            return redirect(edit_url)

        redirect_uri = request.build_absolute_uri(reverse("workflowconnection_openai_oauth_callback"))
        token_payload = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code.strip(),
            "code_verifier": str(session_data.get("verifier") or ""),
            "redirect_uri": redirect_uri,
        }
        client_secret = _connection_secret_value(connection, "oauth_client_secret")
        if client_secret:
            token_payload["client_secret"] = client_secret

        try:
            response_body, _ = _http_json_request(
                method="POST",
                url=token_url,
                headers=_openai_auth_headers(),
                form_body=token_payload,
            )
        except ValidationError as exc:
            messages.error(request, _flatten_validation_error(exc))
            return redirect(edit_url)

        if not isinstance(response_body, dict):
            messages.error(request, "OpenAI OAuth token exchange returned an unexpected response.")
            return redirect(edit_url)

        access_token = response_body.get("access_token")
        refresh_token = response_body.get("refresh_token")
        expires_in = response_body.get("expires_in")
        if (
            not isinstance(access_token, str)
            or not access_token.strip()
            or not isinstance(refresh_token, str)
            or not refresh_token.strip()
        ):
            messages.error(request, "OpenAI OAuth token exchange did not return the required tokens.")
            return redirect(edit_url)

        connection_state = getattr(connection, "state", None)
        if connection_state is None:
            connection_state, _ = WorkflowConnectionState.objects.get_or_create(connection=connection)
            connection.state = connection_state
        state_values = connection_state.state_values or {}
        state_values["access_token"] = access_token.strip()
        state_values["refresh_token"] = refresh_token.strip()
        if expires_in not in (None, ""):
            try:
                state_values["expires_at"] = int(time.time()) + int(expires_in)
            except (TypeError, ValueError):
                pass
        account_id = response_body.get("account_id")
        if isinstance(account_id, str) and account_id.strip():
            state_values["account_id"] = account_id.strip()
        connection_state.state_values = state_values
        connection_state.mark_refreshed()
        connection_state.full_clean()
        connection_state.save()

        messages.success(request, f'Connected OpenAI OAuth account for "{connection.name}".')
        if popup:
            return _build_workflow_connection_popup_response(request, connection, action="oauth_connected")
        return redirect(edit_url)


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
                "workflow_definition": canonicalize_workflow_definition(self.object.definition),
                "workflow_catalog": build_workflow_catalog_payload(),
                "workflow_connection_add_url": (
                    f'{reverse("workflowconnection_add")}?environment={self.object.environment_id}'
                    if self.object.environment_id
                    else reverse("workflowconnection_add")
                ),
                "workflow_connections": _serialize_workflow_connections_for_designer(self.object),
                "workflow_designer_connections_url": reverse("workflow_designer_connections", args=[self.object.pk]),
                "workflow_nodes": normalized_definition.get("nodes", []),
                "workflow_list_url": reverse("workflow_list"),
                "workflow_detail_url": self.object.get_absolute_url(),
                "workflow_designer_save_url": reverse("workflow_designer_save", args=[self.object.pk]),
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


class WorkflowDesignerSaveView(View):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        try:
            payload = _parse_json_request_payload(request)
            if "definition" not in payload:
                raise ValidationError({"definition": "This field is required."})
            revision = payload.get("revision")
            revision_value = None
            if revision not in (None, ""):
                if not isinstance(revision, int):
                    raise ValidationError({"revision": "Revision must be an integer."})
                if revision < 0:
                    raise ValidationError({"revision": "Revision must be zero or greater."})
                revision_value = revision

            with transaction.atomic():
                workflow = (
                    Workflow.objects.select_for_update()
                    .order_by("pk")
                    .filter(pk=kwargs["pk"])
                    .first()
                )
                if workflow is None:
                    return JsonResponse({"detail": "Workflow not found."}, status=404)

                assert_object_action_allowed(workflow, request=request, action="change")
                latest_revision = 0
                if isinstance(workflow.definition, dict):
                    persisted_revision = workflow.definition.get("autosave_revision")
                    if isinstance(persisted_revision, int) and persisted_revision >= 0:
                        latest_revision = persisted_revision

                if revision_value is not None and revision_value < latest_revision:
                    return JsonResponse(
                        {
                            "detail": "Stale autosave ignored.",
                            "stale": True,
                            "workflow": {
                                "edge_count": workflow.edge_count,
                                "id": workflow.pk,
                                "node_count": workflow.node_count,
                            },
                        }
                    )

                next_definition = payload["definition"]
                if revision_value is not None and isinstance(next_definition, dict):
                    next_definition = {
                        **next_definition,
                        "autosave_revision": revision_value,
                    }
                form = WorkflowDesignerForm(
                    data={"definition": json.dumps(next_definition)},
                    instance=workflow,
                )
                if not form.is_valid():
                    raise _build_form_validation_error(form)
                workflow = form.save()
        except ValidationError as exc:
            return JsonResponse({"detail": _flatten_validation_error(exc)}, status=400)

        return JsonResponse(
            {
                "detail": "Workflow saved.",
                "workflow": {
                    "edge_count": workflow.edge_count,
                    "id": workflow.pk,
                    "node_count": workflow.node_count,
                },
            }
        )


class WorkflowDesignerConnectionsView(View):
    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        workflow = (
            Workflow.objects.select_related("organization", "workspace", "environment")
            .filter(pk=kwargs["pk"])
            .first()
        )
        if workflow is None:
            return JsonResponse({"detail": "Workflow not found."}, status=404)

        assert_object_action_allowed(workflow, request=request, action="change")
        return JsonResponse({"connections": _serialize_workflow_connections_for_designer(workflow)})


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
