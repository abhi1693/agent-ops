from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from automation.catalog.services import get_catalog_connection_type
from automation.models import WorkflowConnection, WorkflowConnectionState
from automation.tools.base import _http_json_request


@dataclass(frozen=True)
class WorkflowResolvedConnection:
    connection: WorkflowConnection
    values: dict[str, Any]
    secret_metas: dict[str, dict[str, str | None]]


@dataclass(frozen=True)
class WorkflowResolvedRequestAuth:
    headers: dict[str, str]
    query: dict[str, str]


def _build_scope_queryset(runtime):
    queryset = WorkflowConnection.objects.select_related(
        "secret_group",
        "state",
    ).filter(
        organization=runtime.workflow.organization,
        enabled=True,
    )

    if runtime.workflow.environment_id:
        return queryset.filter(
            Q(environment=runtime.workflow.environment)
            | Q(environment__isnull=True, workspace=runtime.workflow.workspace)
            | Q(environment__isnull=True, workspace__isnull=True, organization=runtime.workflow.organization)
        )

    if runtime.workflow.workspace_id:
        return queryset.filter(
            Q(workspace=runtime.workflow.workspace, environment__isnull=True)
            | Q(workspace__isnull=True, environment__isnull=True, organization=runtime.workflow.organization)
        )

    return queryset.filter(
        workspace__isnull=True,
        environment__isnull=True,
    )


def _oauth_refresh_headers(connection: WorkflowConnection) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if connection.connection_type == "openai.api":
        headers["User-Agent"] = "agent-ops-openai-auth/1.0"
    return headers


def _get_connection(runtime, *, connection_id: str | int | None, expected_connection_type: str | None) -> WorkflowConnection:
    if connection_id in (None, ""):
        raise ValidationError({"definition": f'Node "{runtime.node["id"]}" must define config.connection_id.'})

    queryset = _build_scope_queryset(runtime)

    try:
        connection = queryset.get(pk=connection_id)
    except WorkflowConnection.DoesNotExist as exc:
        raise ValidationError(
            {"definition": f'Node "{runtime.node["id"]}" references unavailable connection "{connection_id}".'}
        ) from exc

    if expected_connection_type and connection.connection_type != expected_connection_type:
        raise ValidationError(
            {
                "definition": (
                    f'Node "{runtime.node["id"]}" requires connection type "{expected_connection_type}", '
                    f'but received "{connection.connection_type}".'
                )
            }
        )

    return connection


def _resolve_secret_value(runtime, *, connection: WorkflowConnection, field_key: str, secret) -> tuple[str, dict[str, str | None]]:
    secret_value = secret.get_value(obj=runtime.workflow)
    if not isinstance(secret_value, str) or not secret_value:
        raise ValidationError(
            {
                "definition": (
                    f'Connection "{connection.name}" secret "{secret.name}" for field "{field_key}" must resolve '
                    "to a non-empty string."
                )
            }
        )

    runtime.secret_values.append(secret_value)
    return (
        secret_value,
        {
            "name": secret.name,
            "provider": secret.provider,
            "secret_group": secret.secret_group.name if secret.secret_group_id else None,
        },
    )


def get_connection_slot_value(
    config: dict[str, Any] | None,
    *,
    slot_key: str = "connection_id",
    multiple: bool = False,
) -> str | int | list[str | int] | None:
    if not isinstance(config, dict):
        return [] if multiple else None

    value = config.get(slot_key)
    if not multiple:
        if value in (None, ""):
            return None
        return value

    if value in (None, "", []):
        return []
    if isinstance(value, list):
        return [item for item in value if item not in (None, "")]
    return [value]


def _auth_condition_matches(*, resolved_connection: WorkflowResolvedConnection, field_key: str | None, values: tuple[str, ...]) -> bool:
    if not field_key:
        return True
    current_value = resolved_connection.values.get(field_key)
    if not values:
        return bool(current_value)
    if not isinstance(current_value, str):
        return False
    return current_value in values


def resolve_workflow_connection_fields(
    runtime,
    *,
    connection_id: str | int | None,
    expected_connection_type: str | None,
) -> WorkflowResolvedConnection:
    connection = _get_connection(
        runtime,
        connection_id=connection_id,
        expected_connection_type=expected_connection_type,
    )
    connection_definition = get_catalog_connection_type(connection.connection_type)
    if connection_definition is None:
        raise ValidationError(
            {"definition": f'Connection "{connection.name}" uses unknown connection type "{connection.connection_type}".'}
        )

    resolved_values: dict[str, Any] = {}
    secret_metas: dict[str, dict[str, str | None]] = {}
    field_values = connection.field_values or {}

    for field_definition in connection_definition.field_schema:
        raw_value = field_values.get(field_definition.key)

        if field_definition.value_type == "secret_ref":
            if raw_value in (None, ""):
                if field_definition.required:
                    raise ValidationError(
                        {
                            "definition": (
                                f'Connection "{connection.name}" must define secret-backed field '
                                f'"{field_definition.key}".'
                            )
                        }
                    )
                continue

            if not isinstance(raw_value, dict):
                raise ValidationError(
                    {
                        "definition": (
                            f'Connection "{connection.name}" field "{field_definition.key}" must be a JSON object '
                            "when using a secret reference."
                        )
                    }
                )

            source = raw_value.get("source", "secret")
            if source != "secret":
                raise ValidationError(
                    {
                        "definition": (
                            f'Connection "{connection.name}" field "{field_definition.key}" must use source '
                            '"secret".'
                        )
                    }
                )

            secret_name = raw_value.get("secret_name")
            if not isinstance(secret_name, str) or not secret_name.strip():
                raise ValidationError(
                    {
                        "definition": (
                            f'Connection "{connection.name}" field "{field_definition.key}" must define a '
                            "non-empty secret_name."
                        )
                    }
                )
            if connection.secret_group is None:
                raise ValidationError(
                    {
                        "definition": (
                            f'Connection "{connection.name}" must define a secret group before using field '
                            f'"{field_definition.key}".'
                        )
                    }
                )

            secret = connection.secret_group.get_secret(name=secret_name.strip())
            if secret is None or not secret.enabled:
                raise ValidationError(
                    {
                        "definition": (
                            f'Connection "{connection.name}" cannot resolve enabled secret "{secret_name.strip()}" '
                            f'for field "{field_definition.key}".'
                        )
                    }
                )

            secret_value, secret_meta = _resolve_secret_value(
                runtime,
                connection=connection,
                field_key=field_definition.key,
                secret=secret,
            )
            resolved_values[field_definition.key] = secret_value
            secret_metas[field_definition.key] = secret_meta
            continue

        if raw_value in (None, ""):
            raw_value = field_definition.default

        if raw_value in (None, ""):
            if field_definition.required:
                raise ValidationError(
                    {
                        "definition": (
                            f'Connection "{connection.name}" must define field "{field_definition.key}".'
                        )
                    }
                )
            continue

        resolved_values[field_definition.key] = raw_value

    return WorkflowResolvedConnection(
        connection=connection,
        values=resolved_values,
        secret_metas=secret_metas,
    )


def build_resolved_connection_request_auth(
    resolved_connection: WorkflowResolvedConnection,
) -> WorkflowResolvedRequestAuth:
    connection_definition = get_catalog_connection_type(resolved_connection.connection.connection_type)
    if connection_definition is None or connection_definition.http_auth is None:
        return WorkflowResolvedRequestAuth(headers={}, query={})

    headers: dict[str, str] = {}
    query: dict[str, str] = {}
    http_auth = connection_definition.http_auth
    if not _auth_condition_matches(
        resolved_connection=resolved_connection,
        field_key=http_auth.enabled_when_field,
        values=http_auth.enabled_when_values,
    ):
        return WorkflowResolvedRequestAuth(headers={}, query={})

    if http_auth.basic_username_field or http_auth.basic_password_field:
        username_field = http_auth.basic_username_field or ""
        password_field = http_auth.basic_password_field or ""
        username = resolved_connection.values.get(username_field)
        password = resolved_connection.values.get(password_field)
        if username_field and password_field:
            if not isinstance(username, str) or not isinstance(password, str) or not username or not password:
                raise ValidationError(
                    {
                        "definition": (
                            f'Connection "{resolved_connection.connection.name}" must define string fields '
                            f'"{username_field}" and "{password_field}" for HTTP basic auth.'
                        )
                    }
                )
            token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {token}"

    for header_definition in http_auth.headers:
        raw_value = resolved_connection.values.get(header_definition.field_key)
        if raw_value in (None, ""):
            if header_definition.required:
                raise ValidationError(
                    {
                        "definition": (
                            f'Connection "{resolved_connection.connection.name}" must define field '
                            f'"{header_definition.field_key}" for header "{header_definition.header_name}".'
                        )
                    }
                )
            continue
        if not isinstance(raw_value, str):
            raise ValidationError(
                {
                    "definition": (
                        f'Connection "{resolved_connection.connection.name}" field "{header_definition.field_key}" '
                        f'must resolve to a string for header "{header_definition.header_name}".'
                    )
                }
            )
        dynamic_prefix = ""
        if header_definition.prefix_field_key:
            prefix_value = resolved_connection.values.get(header_definition.prefix_field_key)
            if prefix_value not in (None, ""):
                if not isinstance(prefix_value, str):
                    raise ValidationError(
                        {
                            "definition": (
                                f'Connection "{resolved_connection.connection.name}" field '
                                f'"{header_definition.prefix_field_key}" must resolve to a string prefix for '
                                f'header "{header_definition.header_name}".'
                            )
                        }
                    )
                dynamic_prefix = f"{prefix_value}{header_definition.prefix_separator}"
        headers[header_definition.header_name] = f"{header_definition.prefix}{dynamic_prefix}{raw_value}"

    for query_definition in http_auth.query:
        raw_value = resolved_connection.values.get(query_definition.field_key)
        if raw_value in (None, ""):
            if query_definition.required:
                raise ValidationError(
                    {
                        "definition": (
                            f'Connection "{resolved_connection.connection.name}" must define field '
                            f'"{query_definition.field_key}" for query parameter "{query_definition.query_param}".'
                        )
                    }
                )
            continue
        if not isinstance(raw_value, str):
            raise ValidationError(
                {
                    "definition": (
                        f'Connection "{resolved_connection.connection.name}" field "{query_definition.field_key}" '
                        f'must resolve to a string for query parameter "{query_definition.query_param}".'
                    )
                }
            )
        query[query_definition.query_param] = raw_value

    return WorkflowResolvedRequestAuth(headers=headers, query=query)


def _oauth_token_is_expiring(expires_at: Any, *, leeway_seconds: int = 60) -> bool:
    if expires_at in (None, ""):
        return True
    try:
        expires_at_int = int(expires_at)
    except (TypeError, ValueError):
        return True
    return expires_at_int <= int(timezone.now().timestamp()) + leeway_seconds


def _get_or_create_connection_state(connection: WorkflowConnection) -> WorkflowConnectionState:
    state = getattr(connection, "state", None)
    if state is not None:
        return state
    state, _ = WorkflowConnectionState.objects.get_or_create(connection=connection)
    connection.state = state
    return state


def _resolve_oauth2_request_auth(
    runtime,
    *,
    resolved_connection: WorkflowResolvedConnection,
) -> WorkflowResolvedRequestAuth:
    connection_definition = get_catalog_connection_type(resolved_connection.connection.connection_type)
    oauth2 = connection_definition.oauth2 if connection_definition is not None else None
    if oauth2 is None:
        return WorkflowResolvedRequestAuth(headers={}, query={})
    if not _auth_condition_matches(
        resolved_connection=resolved_connection,
        field_key=oauth2.enabled_when_field,
        values=oauth2.enabled_when_values,
    ):
        return WorkflowResolvedRequestAuth(headers={}, query={})

    connection = resolved_connection.connection
    state = _get_or_create_connection_state(connection)
    state_values = state.state_values or {}
    access_token = state_values.get(oauth2.access_token_state_key)
    refresh_token = state_values.get(oauth2.refresh_token_state_key)

    if isinstance(access_token, str) and access_token and not _oauth_token_is_expiring(
        state_values.get(oauth2.expires_at_state_key)
    ):
        runtime.secret_values.append(access_token)
        return WorkflowResolvedRequestAuth(
            headers={oauth2.access_token_header_name: f"{oauth2.access_token_prefix}{access_token}"},
            query={},
        )

    if not isinstance(refresh_token, str) or not refresh_token:
        raise ValidationError(
            {
                "definition": (
                    f'Connection "{connection.name}" requires OAuth refresh state field '
                    f'"{oauth2.refresh_token_state_key}" before it can be used.'
                )
            }
        )

    token_url = resolved_connection.values.get(oauth2.token_url_field)
    if not isinstance(token_url, str) or not token_url.strip():
        raise ValidationError(
            {
                "definition": (
                    f'Connection "{connection.name}" must define field "{oauth2.token_url_field}" for OAuth refresh.'
                )
            }
        )

    payload: dict[str, Any] = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    if oauth2.client_id_field:
        client_id = resolved_connection.values.get(oauth2.client_id_field)
        if not isinstance(client_id, str) or not client_id.strip():
            raise ValidationError(
                {
                    "definition": (
                        f'Connection "{connection.name}" must define field "{oauth2.client_id_field}" for OAuth refresh.'
                    )
                }
            )
        payload["client_id"] = client_id
    if oauth2.client_secret_field:
        client_secret = resolved_connection.values.get(oauth2.client_secret_field)
        if isinstance(client_secret, str) and client_secret.strip():
            payload["client_secret"] = client_secret

    response_body, _ = _http_json_request(
        method="POST",
        url=token_url.strip(),
        headers=_oauth_refresh_headers(connection),
        form_body=payload,
    )
    if not isinstance(response_body, dict):
        raise ValidationError(
            {
                "definition": (
                    f'Connection "{connection.name}" OAuth token refresh returned an unexpected non-JSON response.'
                )
            }
        )

    refreshed_access_token = response_body.get("access_token")
    if not isinstance(refreshed_access_token, str) or not refreshed_access_token.strip():
        raise ValidationError(
            {"definition": f'Connection "{connection.name}" OAuth token refresh did not return access_token.'}
        )

    next_refresh_token = response_body.get("refresh_token")
    next_expires_in = response_body.get("expires_in")
    state_values[oauth2.access_token_state_key] = refreshed_access_token.strip()
    state_values[oauth2.refresh_token_state_key] = (
        str(next_refresh_token).strip() if next_refresh_token not in (None, "") else refresh_token
    )
    if next_expires_in not in (None, ""):
        try:
            state_values[oauth2.expires_at_state_key] = int(timezone.now().timestamp()) + int(next_expires_in)
        except (TypeError, ValueError):
            pass
    if oauth2.account_id_state_key and response_body.get("account_id") not in (None, ""):
        state_values[oauth2.account_id_state_key] = str(response_body.get("account_id")).strip()
    state.state_values = state_values
    state.mark_refreshed()
    state.full_clean()
    state.save(update_fields=("state_values", "last_refreshed", "last_updated"))

    runtime.secret_values.append(refreshed_access_token.strip())
    refreshed_refresh_token = state_values.get(oauth2.refresh_token_state_key)
    if isinstance(refreshed_refresh_token, str) and refreshed_refresh_token:
        runtime.secret_values.append(refreshed_refresh_token)
    return WorkflowResolvedRequestAuth(
        headers={oauth2.access_token_header_name: f"{oauth2.access_token_prefix}{refreshed_access_token.strip()}"},
        query={},
    )


def resolve_connection_request_auth(
    runtime,
    *,
    resolved_connection: WorkflowResolvedConnection,
) -> WorkflowResolvedRequestAuth:
    connection_definition = get_catalog_connection_type(resolved_connection.connection.connection_type)
    if connection_definition is None:
        return WorkflowResolvedRequestAuth(headers={}, query={})

    oauth_auth = _resolve_oauth2_request_auth(runtime, resolved_connection=resolved_connection)
    static_auth = build_resolved_connection_request_auth(resolved_connection)
    headers = {**static_auth.headers, **oauth_auth.headers}
    query = {**static_auth.query, **oauth_auth.query}
    return WorkflowResolvedRequestAuth(headers=headers, query=query)


__all__ = (
    "WorkflowResolvedConnection",
    "WorkflowResolvedRequestAuth",
    "build_resolved_connection_request_auth",
    "get_connection_slot_value",
    "resolve_connection_request_auth",
    "resolve_workflow_connection_fields",
)
