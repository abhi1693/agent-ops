from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse

from automation.catalog.services import get_catalog_node
from automation.core_nodes.webhook_trigger.node import get_configured_webhook_path
from automation.primitives import (
    WORKFLOW_DEFINITION_VERSION,
    canonicalize_workflow_definition,
    normalize_workflow_definition_nodes,
    validate_workflow_runtime_definition,
)
from automation.workflow_connections import validate_agent_auxiliary_edges
from core.models import PrimaryModel


def _default_definition():
    return {
        "definition_version": WORKFLOW_DEFINITION_VERSION,
        "nodes": [],
        "edges": [],
        "viewport": {
            "x": 0,
            "y": 0,
            "zoom": 1,
        },
    }


def _derive_scope_from_environment(workspace, environment):
    if environment is not None and workspace is None:
        workspace = environment.workspace
    return workspace


def _derive_scope_from_workspace(organization, workspace):
    if workspace is not None and organization is None:
        organization = workspace.organization
    return organization


def _derive_scope(*, organization, workspace, environment):
    workspace = _derive_scope_from_environment(workspace, environment)
    organization = _derive_scope_from_workspace(organization, workspace)
    return organization, workspace, environment


def _validate_scope_consistency(*, organization, workspace, environment):
    if workspace is not None and organization is not None and workspace.organization_id != organization.pk:
        raise ValidationError(
            {
                "organization": "Organization must match the selected workspace.",
                "workspace": "Workspace belongs to a different organization.",
            }
        )

    if environment is None:
        return

    expected_workspace = environment.workspace
    expected_organization = expected_workspace.organization

    if workspace is not None and workspace.pk != expected_workspace.pk:
        raise ValidationError(
            {
                "workspace": "Workspace must match the selected environment.",
                "environment": "Environment belongs to a different workspace.",
            }
        )

    if organization is not None and organization.pk != expected_organization.pk:
        raise ValidationError(
            {
                "organization": "Organization must match the selected environment.",
                "environment": "Environment belongs to a different organization.",
            }
        )


def _get_scope_related_object(*, organization, workspace, environment):
    if environment is not None:
        return environment
    if workspace is not None:
        return workspace
    return organization


def _validate_unique_scope_name(instance):
    duplicate_qs = instance.__class__.objects.exclude(pk=instance.pk).filter(
        organization=instance.organization,
        workspace=instance.workspace,
        environment=instance.environment,
        name=instance.name,
    )
    if duplicate_qs.exists():
        raise ValidationError({"name": "A workflow with this name already exists for the selected scope."})


def _validate_json_object(value, *, field_name):
    if not isinstance(value, dict):
        raise ValidationError({field_name: "This field must be a JSON object."})


def _validate_workflow_nodes(nodes):
    if not isinstance(nodes, list):
        raise ValidationError({"definition": 'The "nodes" property must be a list.'})

    node_ids = set()
    for index, node in enumerate(nodes, start=1):
        if not isinstance(node, dict):
            raise ValidationError({"definition": f"Node #{index} must be a JSON object."})

        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id.strip():
            raise ValidationError({"definition": f"Node #{index} must define a non-empty string id."})
        if node_id in node_ids:
            raise ValidationError({"definition": f'Node id "{node_id}" is duplicated.'})

        kind = node.get("kind")
        if not isinstance(kind, str) or not kind.strip():
            raise ValidationError({"definition": f'Node "{node_id}" must define a non-empty string kind.'})

        config = node.get("config")
        if config is not None and not isinstance(config, dict):
            raise ValidationError({"definition": f'Node "{node_id}" config must be a JSON object.'})

        node_type = node.get("type")
        if not isinstance(node_type, str) or not node_type.strip():
            raise ValidationError({"definition": f'Node "{node_id}" must define a non-empty string type.'})

        catalog_definition = get_catalog_node(node_type)
        if catalog_definition is None:
            raise ValidationError(
                {
                    "definition": (
                        f'Node "{node_id}" type "{node_type}" is not a supported v2 catalog node type.'
                    )
                }
            )
        expected_kind = _persisted_kind_for_catalog_node(catalog_definition)
        if expected_kind != kind:
            catalog_node_id = getattr(catalog_definition, "id", None) or getattr(catalog_definition, "type", node_type)
            raise ValidationError(
                {
                    "definition": (
                        f'Node "{node_id}" type "{catalog_node_id}" does not match kind "{kind}".'
                    )
                }
            )

        label = node.get("label")
        if label is not None and not isinstance(label, str):
            raise ValidationError({"definition": f'Node "{node_id}" label must be a string.'})

        position = node.get("position")
        if not isinstance(position, dict):
            raise ValidationError({"definition": f'Node "{node_id}" must define a position object.'})

        for axis in ("x", "y"):
            value = position.get(axis)
            if not isinstance(value, int | float):
                raise ValidationError({"definition": f'Node "{node_id}" position.{axis} must be numeric.'})

        node_ids.add(node_id)

    return node_ids


def _persisted_kind_for_catalog_node(node_definition) -> str:
    mode = getattr(node_definition, "mode", None)
    kind = getattr(node_definition, "kind", None)

    if mode == "trigger" or kind == "trigger":
        return "trigger"
    if kind == "agent":
        return "agent"
    if kind in {"output", "response"}:
        return "response"
    if kind in {"control", "condition"}:
        return "condition"
    return "tool"


def _validate_workflow_edges(edges, *, node_ids):
    if not isinstance(edges, list):
        raise ValidationError({"definition": 'The "edges" property must be a list.'})

    edge_ids = set()
    for index, edge in enumerate(edges, start=1):
        if not isinstance(edge, dict):
            raise ValidationError({"definition": f"Edge #{index} must be a JSON object."})

        edge_id = edge.get("id")
        if not isinstance(edge_id, str) or not edge_id.strip():
            raise ValidationError({"definition": f"Edge #{index} must define a non-empty string id."})
        if edge_id in edge_ids:
            raise ValidationError({"definition": f'Edge id "{edge_id}" is duplicated.'})

        for endpoint in ("source", "target"):
            node_id = edge.get(endpoint)
            if not isinstance(node_id, str) or not node_id.strip():
                raise ValidationError({"definition": f'Edge "{edge_id}" must define a non-empty string {endpoint}.'})
            if node_id not in node_ids:
                raise ValidationError({"definition": f'Edge "{edge_id}" references unknown {endpoint} node "{node_id}".'})

        for port_name in ("sourcePort", "targetPort"):
            port_value = edge.get(port_name)
            if port_value is None:
                continue
            if not isinstance(port_value, str) or not port_value.strip():
                raise ValidationError(
                    {"definition": f'Edge "{edge_id}" {port_name} must be a non-empty string when provided.'}
                )

        edge_ids.add(edge_id)


def _validate_workflow_definition(definition):
    _validate_json_object(definition, field_name="definition")
    normalized_definition = normalize_workflow_definition_nodes(definition)
    nodes = normalized_definition.get("nodes")
    edges = normalized_definition.get("edges")
    node_ids = _validate_workflow_nodes(nodes)
    _validate_workflow_edges(edges, node_ids=node_ids)
    if nodes and edges:
        validate_agent_auxiliary_edges(
            nodes_by_id={node["id"]: node for node in nodes},
            edges=edges,
        )
    if nodes or edges:
        validate_workflow_runtime_definition(
            nodes=normalized_definition.get("nodes", []),
            edges=edges,
        )

    viewport = definition.get("viewport")
    if viewport is not None:
        if not isinstance(viewport, dict):
            raise ValidationError({"definition": 'The optional "viewport" property must be a JSON object.'})
        for key in ("x", "y", "zoom"):
            value = viewport.get(key)
            if value is not None and not isinstance(value, int | float):
                raise ValidationError({"definition": f'Viewport "{key}" must be numeric.'})


def _iter_public_webhook_nodes(definition: dict | None) -> list[dict]:
    nodes = normalize_workflow_definition_nodes(definition).get("nodes", [])
    return [node for node in nodes if isinstance(node, dict) and node.get("type") == "core.webhook_trigger"]


def _collect_existing_public_webhook_paths(*, exclude_workflow_pk=None) -> dict[str, str]:
    existing_paths: dict[str, str] = {}
    workflows = Workflow.objects.exclude(pk=exclude_workflow_pk).only("pk", "name", "definition").order_by("pk")
    for workflow in workflows.iterator():
        for node in _iter_public_webhook_nodes(workflow.definition):
            path = get_configured_webhook_path(node.get("config") or {})
            if path:
                existing_paths.setdefault(path, workflow.name)
    return existing_paths


def _assign_public_webhook_paths(definition: dict | None, *, exclude_workflow_pk=None) -> dict:
    if not isinstance(definition, dict):
        return canonicalize_workflow_definition(definition)

    existing_paths = _collect_existing_public_webhook_paths(exclude_workflow_pk=exclude_workflow_pk)
    assigned_paths: dict[str, str] = {}
    used_paths = set(existing_paths)
    normalized_nodes = _iter_public_webhook_nodes(definition)

    for node in normalized_nodes:
        node_id = str(node.get("id") or "").strip()
        if not node_id:
            continue
        path = get_configured_webhook_path(node.get("config") or {})
        if path:
            if path in assigned_paths.values():
                raise ValidationError(
                    {"definition": f'Webhook path "{path}" is duplicated within this workflow.'}
                )
            if path in existing_paths:
                raise ValidationError(
                    {
                        "definition": (
                            f'Webhook path "{path}" is already used by workflow "{existing_paths[path]}".'
                        )
                    }
                )
            assigned_paths[node_id] = path
            used_paths.add(path)
            continue

        path = str(uuid.uuid4())
        while path in used_paths:
            path = str(uuid.uuid4())
        assigned_paths[node_id] = path
        used_paths.add(path)

    updated_definition = canonicalize_workflow_definition(definition)
    updated_nodes = []
    for node in updated_definition.get("nodes", []):
        if not isinstance(node, dict):
            updated_nodes.append(node)
            continue
        node_id = str(node.get("id") or "").strip()
        assigned_path = assigned_paths.get(node_id)
        if not assigned_path:
            updated_nodes.append(node)
            continue
        parameters = dict(node.get("parameters") or {})
        parameters["path"] = assigned_path
        updated_node = dict(node)
        updated_node["parameters"] = parameters
        updated_nodes.append(updated_node)
    updated_definition["nodes"] = updated_nodes
    return updated_definition


class Workflow(PrimaryModel):
    organization = models.ForeignKey(
        "tenancy.Organization",
        on_delete=models.CASCADE,
        related_name="workflows",
        blank=True,
        null=True,
    )
    workspace = models.ForeignKey(
        "tenancy.Workspace",
        on_delete=models.CASCADE,
        related_name="workflows",
        blank=True,
        null=True,
    )
    environment = models.ForeignKey(
        "tenancy.Environment",
        on_delete=models.CASCADE,
        related_name="workflows",
        blank=True,
        null=True,
    )
    name = models.CharField(max_length=150)
    enabled = models.BooleanField(default=True)
    definition = models.JSONField(default=_default_definition, blank=True)

    class Meta:
        ordering = ("organization__name", "workspace__name", "environment__name", "name")
        constraints = (
            models.UniqueConstraint(
                fields=("environment", "name"),
                condition=models.Q(environment__isnull=False),
                name="automation_workflow_unique_environment_name",
            ),
            models.UniqueConstraint(
                fields=("workspace", "name"),
                condition=models.Q(workspace__isnull=False, environment__isnull=True),
                name="automation_workflow_unique_workspace_name",
            ),
            models.UniqueConstraint(
                fields=("organization", "name"),
                condition=models.Q(workspace__isnull=True, environment__isnull=True),
                name="automation_workflow_unique_organization_name",
            ),
        )

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self):
        return reverse("workflow_detail", args=[self.pk])

    @property
    def scope_type(self) -> str:
        if self.environment_id:
            return "Environment"
        if self.workspace_id:
            return "Workspace"
        return "Organization"

    @property
    def scope_label(self) -> str:
        parts = [self.organization.name] if self.organization_id else []
        if self.workspace_id:
            parts.append(self.workspace.name)
        if self.environment_id:
            parts.append(self.environment.name)
        return " / ".join(parts)

    @property
    def node_count(self) -> int:
        nodes = self.definition.get("nodes", []) if isinstance(self.definition, dict) else []
        return len(nodes)

    @property
    def edge_count(self) -> int:
        edges = self.definition.get("edges", []) if isinstance(self.definition, dict) else []
        return len(edges)

    def clean(self):
        super().clean()

        self.organization, self.workspace, self.environment = _derive_scope(
            organization=self.organization,
            workspace=self.workspace,
            environment=self.environment,
        )
        _validate_scope_consistency(
            organization=self.organization,
            workspace=self.workspace,
            environment=self.environment,
        )
        self.definition = _assign_public_webhook_paths(
            self.definition,
            exclude_workflow_pk=self.pk,
        )
        _validate_workflow_definition(self.definition)

        if self.organization is None:
            raise ValidationError({"organization": "A workflow must be scoped to at least an organization."})

        _validate_unique_scope_name(self)

    def save(self, *args, **kwargs):
        self.organization, self.workspace, self.environment = _derive_scope(
            organization=self.organization,
            workspace=self.workspace,
            environment=self.environment,
        )
        original_definition = self.definition
        self.definition = _assign_public_webhook_paths(
            self.definition,
            exclude_workflow_pk=self.pk,
        )
        if kwargs.get("update_fields") is not None and self.definition != original_definition:
            kwargs["update_fields"] = tuple(set(kwargs["update_fields"]) | {"definition"})
        return super().save(*args, **kwargs)

    def get_changelog_related_object(self):
        return _get_scope_related_object(
            organization=self.organization,
            workspace=self.workspace,
            environment=self.environment,
        )
