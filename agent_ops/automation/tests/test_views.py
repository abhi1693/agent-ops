import base64
import hashlib
import hmac
import json
import os
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import jwt
from django.contrib.contenttypes.models import ContentType
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from automation.models import Workflow, WorkflowConnection, WorkflowConnectionState, WorkflowRun, WorkflowStepRun, WorkflowVersion
from automation.primitives import normalize_workflow_definition_nodes
from automation.runtime import execute_workflow_run
from tenancy.models import Environment, Organization, Workspace
from users.models import Membership, ObjectPermission, User


class _FakeJsonResponse:
    def __init__(self, payload, *, status=200, content_type="application/json", headers=None, raw_body=None):
        self._payload = payload
        self._status = status
        self._raw_body = raw_body
        self.headers = {"Content-Type": content_type, **(headers or {})}

    def read(self):
        if self._raw_body is not None:
            return self._raw_body
        return json.dumps(self._payload).encode("utf-8")

    def getcode(self):
        return self._status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _definition(label):
    return {
        "nodes": [
            {
                "id": "trigger-1",
                "kind": "trigger",
                "type": "core.manual_trigger",
                "label": label,
                "position": {"x": 48, "y": 56},
            },
            {
                "id": "response-1",
                "kind": "response",
                "type": "core.response",
                "label": "Return result",
                "config": {
                    "template": "Completed {{ trigger.payload.ticket_id }}",
                },
                "position": {"x": 336, "y": 56},
            },
        ],
        "edges": [
            {
                "id": "edge-1",
                "source": "trigger-1",
                "target": "response-1",
            }
        ],
    }


def _unsupported_definition(label):
    return {
        "nodes": [
            {
                "id": "trigger-1",
                "kind": "trigger",
                "type": "external.manualTrigger",
                "label": label,
                "position": {"x": 48, "y": 56},
            },
            {
                "id": "set-1",
                "kind": "tool",
                "type": "external.set",
                "label": "Unsupported set",
                "config": {
                    "values": {
                        "string": [
                            {
                                "name": "result",
                                "value": "unsupported",
                            }
                        ]
                    }
                },
                "position": {"x": 336, "y": 56},
            },
        ],
        "edges": [
            {
                "id": "edge-1",
                "source": "trigger-1",
                "target": "set-1",
            }
        ],
    }


class WorkflowViewTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="operator",
            email="operator@example.com",
            password="correct-horse-battery-staple",
            is_staff=True,
        )
        self.standard_user = User.objects.create_user(
            username="viewer",
            email="viewer@example.com",
            password="correct-horse-battery-staple",
        )
        self.organization = Organization.objects.create(name="Acme", description="Primary tenant")
        self.workspace = Workspace.objects.create(
            organization=self.organization,
            name="Operations",
            description="Operational workspace",
        )
        self.environment = Environment.objects.create(
            workspace=self.workspace,
            name="production",
            description="Production environment",
        )
        self.other_organization = Organization.objects.create(name="Beta", description="Secondary tenant")
        self.other_workspace = Workspace.objects.create(
            organization=self.other_organization,
            name="Security",
            description="Security workspace",
        )
        self.other_environment = Environment.objects.create(
            workspace=self.other_workspace,
            name="staging",
            description="Staging environment",
        )
        self.membership = Membership.objects.create(
            user=self.standard_user,
            organization=self.organization,
            workspace=self.workspace,
            is_default=True,
        )
        self.workflow_content_type = ContentType.objects.get_for_model(Workflow)
        self.workflow = Workflow.objects.create(
            environment=self.environment,
            name="Intake triage",
            description="Route new work into the agentic intake path.",
            definition=_definition("New task"),
        )
        self.other_workflow = Workflow.objects.create(
            environment=self.other_environment,
            name="Security escalation",
            definition=_definition("Suspicious activity"),
        )

    def _queue_workflow_request(self, request_callable):
        with patch("automation.runtime.ensure_workers_for_queue"), patch(
            "automation.runtime.enqueue_workflow_run_job",
            side_effect=lambda run: run,
        ):
            response = request_callable()

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["status"], WorkflowRun.StatusChoices.PENDING)
        run = WorkflowRun.objects.get(pk=payload["run_id"])
        return response, payload, run

    def _create_connection(self, *, data=None, **kwargs):
        connection = WorkflowConnection.objects.create(**kwargs)
        if data:
            connection.set_data_values(data)
            connection.save(update_fields=("data",))
        return connection

    def _attach_openai_connection(self, workflow, *, node_id="model-1", api_key="sk-test-openai", name=None):
        connection = self._create_connection(
            environment=self.environment,
            name=name or f"{workflow.name} OpenAI",
            integration_id="openai",
            connection_type="openai.api",
            data={
                "auth_mode": "api_key",
                "base_url": "https://api.openai.com/v1",
                "api_key": api_key,
            },
        )
        node = next(item for item in workflow.definition.get("nodes", []) if item.get("id") == node_id)
        config = dict(node.get("config") or {})
        config.pop("connection_id", None)
        config.pop("base_url", None)
        config.pop("secret_name", None)
        config.pop("secret_group_id", None)
        config["connection_id"] = str(connection.pk)
        node["config"] = config
        workflow.save(update_fields=("definition",))
        return connection

    def _get_public_webhook_path(self, workflow, *, node_id=None):
        nodes = normalize_workflow_definition_nodes(workflow.definition or {}).get("nodes", [])
        for node in nodes:
            if node.get("type") != "core.webhook_trigger":
                continue
            if node_id is not None and node.get("id") != node_id:
                continue
            path = (node.get("config") or {}).get("path")
            if isinstance(path, str) and path.strip():
                return path.strip().strip("/")
        raise AssertionError(f"Workflow {workflow.pk} does not define a public webhook path.")

    def _get_public_webhook_url(self, workflow, *, node_id=None):
        return reverse(
            "workflow_webhook_trigger_public",
            args=[self._get_public_webhook_path(workflow, node_id=node_id)],
        )

    def test_workflow_list_is_scoped_for_members(self):
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("workflow_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.workflow.name)
        self.assertNotContains(response, self.other_workflow.name)

    def test_workflow_detail_shows_summary_and_designer_link(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("workflow_detail", args=[self.workflow.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.workflow.name)
        self.assertContains(response, "Open designer")
        self.assertContains(response, "Nodes")
        self.assertContains(response, "Edges")
        self.assertContains(response, "Manual run")
        self.assertContains(response, reverse("workflow_designer", args=[self.workflow.pk]))

    def test_workflow_add_requires_explicit_add_permission(self):
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("workflow_add"))

        self.assertEqual(response.status_code, 403)

    def test_workflow_add_form_uses_scoped_choices_when_permission_granted(self):
        permission = ObjectPermission.objects.create(
            name="Scoped workflow add form",
            actions=["add"],
            constraints={"organization": "$organization"},
        )
        permission.content_types.add(self.workflow_content_type)
        self.membership.object_permissions.add(permission)
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("workflow_add"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.organization.name)
        self.assertContains(response, self.workspace.name)
        self.assertContains(response, self.environment.name)
        self.assertNotContains(response, self.other_organization.name)
        self.assertNotContains(response, self.other_workspace.name)
        self.assertNotContains(response, self.other_environment.name)

    def test_workflow_add_creates_empty_draft_without_definition_errors(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("workflow_add"),
            {
                "environment": self.environment.pk,
                "name": "Draft workflow",
                "description": "Created before the graph is designed.",
                "enabled": "on",
            },
        )

        workflow = Workflow.objects.get(name="Draft workflow")
        self.assertEqual(workflow.definition["definition_version"], 2)
        self.assertRedirects(response, workflow.get_absolute_url())
        self.assertEqual(workflow.definition["nodes"], [])
        self.assertEqual(workflow.definition["edges"], [])

    def test_workflow_designer_requires_change_permission_for_scoped_members(self):
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("workflow_designer", args=[self.workflow.pk]))

        self.assertEqual(response.status_code, 403)

    def test_workflow_designer_renders_existing_nodes_as_connection_options(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("workflow_designer", args=[self.workflow.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="workflow-definition-data"')
        self.assertContains(response, 'id="workflow-catalog-data"')
        self.assertContains(response, 'id="workflow-connections-data"')
        self.assertContains(response, "data-workflow-board")
        self.assertContains(response, "Add node")
        self.assertContains(response, '"catalog_section": "triggers"')
        self.assertContains(response, '"catalog_section": "flow"')
        self.assertContains(response, '"catalog_section": "data"')
        self.assertContains(response, '"catalog_section": "apps"')
        self.assertContains(response, '"app_label": "Core"')
        self.assertContains(response, '"app_label": "GitHub"')
        self.assertContains(response, '"app_label": "Prometheus"')
        self.assertContains(response, '"app_label": "Elasticsearch"')
        self.assertContains(response, '"app_label": "OpenAI"')
        self.assertContains(response, '"type": "core.manual_trigger"')
        self.assertContains(response, '"type": "core.schedule_trigger"')
        self.assertContains(response, '"type": "core.webhook_trigger"')
        self.assertContains(response, '"type": "core.agent"')
        self.assertContains(response, '"type": "core.set"')
        self.assertContains(response, '"type": "core.if"')
        self.assertContains(response, '"type": "core.switch"')
        self.assertContains(response, '"type": "core.response"')
        self.assertContains(response, '"type": "core.stop_and_error"')
        self.assertContains(response, '"type": "github.trigger.webhook"')
        self.assertContains(response, '"type": "prometheus.action.query"')
        self.assertContains(response, '"type": "elasticsearch.action.search"')
        self.assertContains(response, '"type": "openai.model.chat"')
        self.assertNotContains(response, '"type": "deepseek.model.chat"')
        self.assertNotContains(response, '"type": "groq.model.chat"')
        self.assertNotContains(response, '"type": "mistral.model.chat"')
        self.assertNotContains(response, '"type": "openrouter.model.chat"')
        self.assertNotContains(response, '"type": "xai.model.chat"')
        self.assertNotContains(response, '"type": "fireworks.model.chat"')
        self.assertContains(response, '"name": "New task"')
        self.assertContains(response, '"name": "Return result"')
        self.assertContains(response, 'data-workflow-run')
        self.assertContains(response, 'data-workflow-execution-status')
        self.assertContains(response, reverse("workflow_designer_run", args=[self.workflow.pk]))
        self.assertContains(response, reverse("workflow_designer_node_run", args=[self.workflow.pk, "__node_id__"]))
        self.assertContains(response, reverse("workflow_webhook_trigger_public_base"))
        self.assertNotContains(response, reverse("workflow_webhook_trigger_legacy", args=[self.workflow.pk]))

    def test_workflow_designer_rejects_legacy_native_model_provider_nodes(self):
        self.workflow.definition = {
            "nodes": [
                {
                    "id": "trigger-1",
                    "kind": "trigger",
                    "type": "core.manual_trigger",
                    "label": "Manual trigger",
                    "position": {"x": 48, "y": 56},
                },
                {
                    "id": "agent-1",
                    "kind": "agent",
                    "type": "core.agent",
                    "label": "AI Agent",
                    "position": {"x": 336, "y": 56},
                },
                {
                    "id": "model-1",
                    "kind": "tool",
                    "type": "deepseek.model.chat",
                    "label": "DeepSeek",
                    "config": {
                        "base_url": "https://api.deepseek.com/v1",
                        "model": "deepseek-chat",
                    },
                    "position": {"x": 336, "y": 224},
                },
            ],
            "edges": [
                {"id": "edge-1", "source": "trigger-1", "target": "agent-1"},
                {
                    "id": "edge-2",
                    "source": "model-1",
                    "sourcePort": "ai_languageModel",
                    "target": "agent-1",
                    "targetPort": "ai_languageModel",
                },
            ],
        }
        self.workflow.save(update_fields=("definition",))
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("workflow_designer", args=[self.workflow.pk]))

        self.assertRedirects(response, self.workflow.get_absolute_url())
        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertTrue(
            any("only supports v2 catalog nodes" in message for message in messages),
            messages,
        )

    def test_workflow_designer_redirects_unsupported_workflow_to_detail(self):
        self.workflow.definition = _unsupported_definition("Unsupported task")
        self.workflow.save(update_fields=("definition",))
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("workflow_designer", args=[self.workflow.pk]))

        self.assertRedirects(response, self.workflow.get_absolute_url())
        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertTrue(
            any("only supports v2 catalog nodes" in message for message in messages),
            messages,
        )

    def test_workflow_designer_renders_scoped_connections(self):
        WorkflowConnection.objects.create(
            environment=self.environment,
            name="Primary OpenAI",
            integration_id="openai",
            connection_type="openai.api",
        )
        WorkflowConnection.objects.create(
            environment=self.other_environment,
            name="Other scope",
            integration_id="openai",
            connection_type="openai.api",
        )
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("workflow_designer", args=[self.workflow.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["workflow_connections"]), 1)
        workflow_connection = response.context["workflow_connections"][0]
        self.assertEqual(workflow_connection["connection_type"], "openai.api")
        self.assertTrue(workflow_connection["enabled"])
        self.assertEqual(workflow_connection["integration_id"], "openai")
        self.assertEqual(workflow_connection["label"], "Primary OpenAI (Acme / Operations / production)")
        self.assertEqual(workflow_connection["name"], "Primary OpenAI")
        self.assertEqual(workflow_connection["scope_label"], "Acme / Operations / production")
        self.assertTrue(workflow_connection["edit_url"].endswith(f"/workflow-connections/{workflow_connection['id']}/edit/"))
        self.assertTrue(workflow_connection["supports_oauth"])
        catalog_definition = next(
            item
            for item in response.context["workflow_catalog"]["definitions"]
            if item["type"] == "openai.model.chat"
        )
        self.assertEqual(
            [section["id"] for section in response.context["workflow_catalog"]["sections"]],
            ["triggers", "flow", "data", "apps"],
        )
        self.assertEqual(
            [category["id"] for category in response.context["workflow_catalog"]["groups"]],
            ["ai", "data", "flow", "core"],
        )
        self.assertEqual(
            response.context["workflow_catalog"]["presentation"]["settings"]["groups"]["identity"]["title"],
            "Identity",
        )
        self.assertEqual(
            response.context["workflow_catalog"]["presentation"]["node_selection"]["app_actions"]["title"],
            "Action in an app",
        )
        self.assertEqual(
            response.context["workflow_catalog"]["presentation"]["execution"]["run_button"]["idle"],
            "Run node",
        )
        self.assertEqual(
            response.context["workflow_catalog"]["presentation"]["chrome"]["settings_panel"]["title"],
            "Node settings",
        )
        self.assertEqual(catalog_definition["connection_type"], "openai.api")
        self.assertEqual(catalog_definition["connection_slots"][0]["key"], "connection_id")
        self.assertEqual(catalog_definition["connection_slots"][0]["allowed_connection_types"], ["openai.api"])
        self.assertEqual(catalog_definition["app_label"], "OpenAI")
        self.assertEqual(catalog_definition["group"], "app_action")

    def test_workflow_connection_list_is_scoped_for_members(self):
        WorkflowConnection.objects.create(
            environment=self.environment,
            name="OpenAI primary",
            integration_id="openai",
            connection_type="openai.api",
        )
        WorkflowConnection.objects.create(
            environment=self.other_environment,
            name="Other scope",
            integration_id="openai",
            connection_type="openai.api",
        )
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("workflowconnection_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "OpenAI primary")
        self.assertNotContains(response, "Other scope")

    def test_workflow_connection_add_creates_connection_with_derived_scope(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("workflowconnection_add"),
            {
                "environment": self.environment.pk,
                "name": "Primary OpenAI",
                "description": "Main model connection",
                "connection_type": "openai.api",
                "enabled": "on",
                "openai_auth_mode": "api_key",
                "openai_base_url": "https://api.openai.com/v1",
                "openai_api_key": "sk-test-openai",
                "metadata": json.dumps({"owner": "automation"}),
            },
        )

        connection = WorkflowConnection.objects.get(name="Primary OpenAI")
        self.assertRedirects(response, connection.get_absolute_url())
        self.assertEqual(connection.environment_id, self.environment.pk)
        self.assertEqual(connection.workspace_id, self.workspace.pk)
        self.assertEqual(connection.organization_id, self.organization.pk)
        self.assertEqual(connection.integration_id, "openai")
        self.assertEqual(connection.get_data_values()["auth_mode"], "api_key")
        self.assertEqual(connection.get_data_values()["api_key"], "sk-test-openai")

    def test_workflow_connection_add_accepts_openai_oauth_state_values(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("workflowconnection_add"),
            {
                "environment": self.environment.pk,
                "name": "OAuth OpenAI",
                "description": "OpenAI via OAuth refresh flow",
                "connection_type": "openai.api",
                "enabled": "on",
                "data": json.dumps(
                    {
                        "auth_mode": "oauth2_authorization_code",
                        "base_url": "https://api.openai.com/v1",
                        "oauth_client_id": "client-openai-123",
                        "oauth_token_url": "https://auth.openai.com/oauth/token",
                    }
                ),
                "state_values": json.dumps(
                    {
                        "refresh_token": "oauth-refresh-live",
                        "access_token": "oauth-access-live",
                        "expires_at": 4102444800,
                        "account_id": "acct_live",
                    }
                ),
                "metadata": json.dumps({"owner": "automation"}),
            },
        )

        connection = WorkflowConnection.objects.get(name="OAuth OpenAI")
        state = WorkflowConnectionState.objects.get(connection=connection)
        self.assertRedirects(response, connection.get_absolute_url())
        self.assertEqual(state.state_values["refresh_token"], "oauth-refresh-live")
        self.assertEqual(state.state_values["account_id"], "acct_live")

    def test_workflow_connection_add_creates_prometheus_connection_from_structured_fields(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("workflowconnection_add"),
            {
                "environment": self.environment.pk,
                "name": "Primary Prometheus",
                "description": "Metrics API",
                "connection_type": "prometheus.api",
                "enabled": "on",
                "prometheus_base_url": "https://prometheus.example.com",
                "prometheus_bearer_token": "prom-secret",
                "metadata": json.dumps({"owner": "automation"}),
            },
        )

        connection = WorkflowConnection.objects.get(name="Primary Prometheus")
        self.assertRedirects(response, connection.get_absolute_url())
        self.assertEqual(
            connection.get_data_values(),
            {
                "base_url": "https://prometheus.example.com",
                "bearer_token": "prom-secret",
            },
        )

    def test_workflow_connection_add_creates_elasticsearch_connection_from_structured_fields(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("workflowconnection_add"),
            {
                "environment": self.environment.pk,
                "name": "Primary Elasticsearch",
                "description": "Search API",
                "connection_type": "elasticsearch.api",
                "enabled": "on",
                "elasticsearch_base_url": "https://elastic.example.com",
                "elasticsearch_auth_scheme": "Bearer",
                "elasticsearch_auth_token": "elastic-secret",
                "metadata": json.dumps({"owner": "automation"}),
            },
        )

        connection = WorkflowConnection.objects.get(name="Primary Elasticsearch")
        self.assertRedirects(response, connection.get_absolute_url())
        self.assertEqual(
            connection.get_data_values(),
            {
                "base_url": "https://elastic.example.com",
                "auth_scheme": "Bearer",
                "auth_token": "elastic-secret",
            },
        )

    def test_workflow_connection_add_creates_github_connection_from_structured_fields(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("workflowconnection_add"),
            {
                "environment": self.environment.pk,
                "name": "Primary GitHub",
                "description": "Webhook auth",
                "connection_type": "github.oauth2",
                "enabled": "on",
                "github_webhook_secret": "github-secret",
                "metadata": json.dumps({"owner": "automation"}),
            },
        )

        connection = WorkflowConnection.objects.get(name="Primary GitHub")
        self.assertRedirects(response, connection.get_absolute_url())
        self.assertEqual(connection.get_data_values(), {"webhook_secret": "github-secret"})

    def test_workflow_connection_add_creates_webhook_header_auth_connection_from_structured_fields(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("workflowconnection_add"),
            {
                "environment": self.environment.pk,
                "name": "Primary Webhook Header",
                "description": "Generic webhook auth",
                "connection_type": "webhook.header_auth",
                "enabled": "on",
                "webhook_header_auth_name": "X-Webhook-Secret",
                "webhook_header_auth_value": "shared-secret",
                "metadata": json.dumps({"owner": "automation"}),
            },
        )

        connection = WorkflowConnection.objects.get(name="Primary Webhook Header")
        self.assertRedirects(response, connection.get_absolute_url())
        self.assertEqual(
            connection.get_data_values(),
            {
                "name": "X-Webhook-Secret",
                "value": "shared-secret",
            },
        )

    def test_workflow_connection_add_defaults_openai_device_client_for_oauth_mode(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("workflowconnection_add"),
            {
                "environment": self.environment.pk,
                "name": "OAuth OpenAI",
                "description": "OpenAI via OAuth refresh flow",
                "connection_type": "openai.api",
                "enabled": "on",
                "openai_auth_mode": "oauth2_authorization_code",
                "openai_base_url": "https://api.openai.com/v1",
                "openai_oauth_token_url": "https://auth.openai.com/oauth/token",
            },
        )

        connection = WorkflowConnection.objects.get(name="OAuth OpenAI")
        self.assertRedirects(response, connection.get_absolute_url())
        self.assertEqual(connection.get_data_values()["oauth_client_id"], "app_EMoamEEZ73f0CkXaXp7hrann")

    def test_workflow_connection_detail_renders_state_summary_only(self):
        connection = self._create_connection(
            environment=self.environment,
            name="OAuth OpenAI",
            integration_id="openai",
            connection_type="openai.api",
            data={
                "auth_mode": "oauth2_authorization_code",
                "base_url": "https://api.openai.com/v1",
                "oauth_client_id": "client-openai-123",
                "oauth_token_url": "https://auth.openai.com/oauth/token",
            },
        )
        WorkflowConnectionState.objects.create(
            connection=connection,
            state_values={
                "refresh_token": "oauth-refresh-live",
                "access_token": "oauth-access-live",
                "expires_at": 4102444800,
                "account_id": "acct_live",
            },
        )
        self.client.force_login(self.staff_user)

        response = self.client.get(connection.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "State summary")
        self.assertContains(response, "acct_live")
        self.assertContains(response, "has_access_token")
        self.assertNotContains(response, "oauth-refresh-live")
        self.assertNotContains(response, "oauth-access-live")

    def test_workflow_connection_edit_renders_openai_oauth_controls(self):
        connection = self._create_connection(
            environment=self.environment,
            name="OAuth OpenAI",
            integration_id="openai",
            connection_type="openai.api",
            data={
                "auth_mode": "oauth2_authorization_code",
                "base_url": "https://api.openai.com/v1",
                "oauth_token_url": "https://auth.openai.com/oauth/token",
            },
        )
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("workflowconnection_edit", args=[connection.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Connect my account")
        self.assertContains(response, "Auth Mode")
        self.assertContains(response, "API Key")
        self.assertContains(response, "OAuth Client ID")
        self.assertContains(response, "This hosted flow does not require a callback URL")
        self.assertContains(response, "https://auth.openai.com/codex/device")
        self.assertNotContains(response, "Store typed connection field values and metadata as JSON objects.")

    def test_workflow_connection_edit_renders_prometheus_structured_fields(self):
        connection = self._create_connection(
            environment=self.environment,
            name="Prometheus",
            integration_id="prometheus",
            connection_type="prometheus.api",
            data={
                "base_url": "https://prometheus.example.com",
                "bearer_token": "prom-secret",
            },
        )
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("workflowconnection_edit", args=[connection.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Configure the saved Prometheus credential without editing raw JSON.")
        self.assertContains(response, "Bearer Token")
        self.assertNotContains(response, "Store the encrypted connection payload directly on the connection record.")

    def test_workflow_connection_edit_renders_elasticsearch_structured_fields(self):
        connection = self._create_connection(
            environment=self.environment,
            name="Elasticsearch",
            integration_id="elasticsearch",
            connection_type="elasticsearch.api",
            data={
                "base_url": "https://elastic.example.com",
                "auth_scheme": "ApiKey",
                "auth_token": "elastic-secret",
            },
        )
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("workflowconnection_edit", args=[connection.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Configure the saved Elasticsearch credential without editing raw JSON.")
        self.assertContains(response, "Auth Scheme")
        self.assertContains(response, "Auth Token")

    def test_workflow_connection_edit_renders_github_structured_fields(self):
        connection = self._create_connection(
            environment=self.environment,
            name="GitHub",
            integration_id="github",
            connection_type="github.oauth2",
            data={
                "webhook_secret": "github-secret",
            },
        )
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("workflowconnection_edit", args=[connection.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Configure the saved GitHub credential without editing raw JSON.")
        self.assertContains(response, "Webhook Secret")

    def test_workflow_connection_edit_renders_webhook_basic_auth_structured_fields(self):
        connection = self._create_connection(
            environment=self.environment,
            name="Webhook Basic Auth",
            integration_id="webhook",
            connection_type="webhook.basic_auth",
            data={
                "username": "operator",
                "password": "secret-password",
            },
        )
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("workflowconnection_edit", args=[connection.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Configure the saved Basic Auth credential without editing raw JSON.")
        self.assertContains(response, "Username")
        self.assertContains(response, "Password")

    def test_workflow_connection_edit_renders_webhook_header_auth_structured_fields(self):
        connection = self._create_connection(
            environment=self.environment,
            name="Webhook Header Auth",
            integration_id="webhook",
            connection_type="webhook.header_auth",
            data={
                "name": "X-Webhook-Secret",
                "value": "shared-secret",
            },
        )
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("workflowconnection_edit", args=[connection.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Configure the saved Header Auth credential without editing raw JSON.")
        self.assertContains(response, "Name")
        self.assertContains(response, "Value")

    def test_workflow_connection_edit_renders_webhook_jwt_auth_structured_fields(self):
        connection = self._create_connection(
            environment=self.environment,
            name="Webhook JWT Auth",
            integration_id="webhook",
            connection_type="webhook.jwt_auth",
            data={
                "key_type": "passphrase",
                "secret": "jwt-secret",
                "algorithm": "HS256",
            },
        )
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("workflowconnection_edit", args=[connection.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Configure the saved JWT Auth credential without editing raw JSON.")
        self.assertContains(response, "Key Type")
        self.assertContains(response, "Algorithm")
        self.assertContains(response, "Secret")

    def test_workflow_connection_edit_renders_webhook_shared_secret_structured_fields(self):
        connection = self._create_connection(
            environment=self.environment,
            name="Webhook Shared Secret",
            integration_id="webhook",
            connection_type="webhook.shared_secret",
            data={
                "header_name": "X-Webhook-Secret",
                "secret_value": "shared-secret",
            },
        )
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("workflowconnection_edit", args=[connection.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Configure the saved Header Auth credential without editing raw JSON.")
        self.assertContains(response, "Name")
        self.assertContains(response, "Value")

    def test_workflow_connection_popup_uses_minimal_credential_form(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(
            reverse("workflowconnection_add"),
            {
                "popup": "1",
                "environment": str(self.environment.pk),
                "connection_type": "webhook.header_auth",
                "return_url": reverse("workflow_designer", args=[self.workflow.pk]),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add credential")
        self.assertContains(response, "Credentials")
        self.assertContains(response, "Name")
        self.assertContains(response, "Value")
        self.assertNotContains(response, '<label class="col-lg-3 col-form-label" for="id_environment">', html=False)
        self.assertNotContains(response, '<label class="col-lg-3 col-form-label" for="id_description">', html=False)
        self.assertNotContains(response, '<label class="col-lg-3 col-form-label" for="id_enabled">', html=False)
        self.assertNotContains(response, "Store the encrypted connection payload directly on the connection record.")

    def test_workflow_connection_oauth_start_renders_device_login_page(self):
        connection = self._create_connection(
            environment=self.environment,
            name="OAuth OpenAI",
            integration_id="openai",
            connection_type="openai.api",
            data={
                "auth_mode": "oauth2_authorization_code",
                "base_url": "https://api.openai.com/v1",
                "oauth_client_id": "client-openai-123",
                "oauth_token_url": "https://auth.openai.com/oauth/token",
            },
        )
        self.client.force_login(self.staff_user)

        with patch(
            "automation.views._http_json_request",
            return_value=(
                {
                    "device_auth_id": "deviceauth_123",
                    "user_code": "ABCD-EFGH",
                    "interval": "5",
                    "expires_at": "2099-01-01T00:00:00+00:00",
                },
                200,
            ),
        ) as mocked_request:
            response = self.client.get(
                reverse("workflowconnection_openai_oauth_start", args=[connection.pk]),
                {
                    "popup": "1",
                    "return_url": reverse("workflow_designer", args=[self.workflow.pk]),
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Connect OpenAI Account")
        self.assertContains(response, "ABCD-EFGH")
        self.assertContains(response, "https://auth.openai.com/codex/device")
        self.assertContains(response, "oauth/openai/device")
        mocked_request.assert_called_once()
        self.assertEqual(mocked_request.call_args.kwargs["url"], "https://auth.openai.com/api/accounts/deviceauth/usercode")
        self.assertEqual(
            mocked_request.call_args.kwargs["headers"]["User-Agent"],
            "agent-ops-openai-auth/1.0",
        )
        self.assertEqual(
            mocked_request.call_args.kwargs["json_body"],
            {"client_id": "client-openai-123"},
        )

    def test_workflow_connection_oauth_poll_updates_state_and_returns_popup_bridge(self):
        connection = self._create_connection(
            environment=self.environment,
            name="OAuth OpenAI",
            integration_id="openai",
            connection_type="openai.api",
            data={
                "auth_mode": "oauth2_authorization_code",
                "base_url": "https://api.openai.com/v1",
                "oauth_client_id": "client-openai-123",
                "oauth_token_url": "https://auth.openai.com/oauth/token",
            },
        )
        self.client.force_login(self.staff_user)
        with patch(
            "automation.views._http_json_request",
            return_value=(
                {
                    "device_auth_id": "deviceauth_123",
                    "user_code": "ABCD-EFGH",
                    "interval": "5",
                    "expires_at": "2099-01-01T00:00:00+00:00",
                },
                200,
            ),
        ):
            start_response = self.client.get(
                reverse("workflowconnection_openai_oauth_start", args=[connection.pk]),
                {
                    "popup": "1",
                    "return_url": reverse("workflow_designer", args=[self.workflow.pk]),
                },
            )

        self.assertEqual(start_response.status_code, 200)
        session_token = next(
            key.split(":")[-1]
            for key in self.client.session.keys()
            if key.startswith("workflow_connection_openai_oauth:")
        )

        with patch(
            "automation.views._http_json_request",
            side_effect=[
                (
                    {
                        "authorization_code": "oauth-code-new",
                        "code_verifier": "oauth-verifier-new",
                    },
                    200,
                ),
                (
                    {
                        "access_token": "oauth-access-new",
                        "refresh_token": "oauth-refresh-new",
                        "id_token": (
                            "header."
                            "eyJodHRwczovL2FwaS5vcGVuYWkuY29tL2F1dGgiOnsiY2hhdGdwdF9hY2NvdW50X2lkIjoiYWNjdF9uZXcifX0."
                            "signature"
                        ),
                        "expires_in": 3600,
                    },
                    200,
                ),
            ],
        ):
            response = self.client.get(
                reverse("workflowconnection_openai_oauth_poll", args=[session_token]),
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "authorized")
        self.assertIn(reverse("workflowconnection_popup_complete", args=[connection.pk]), payload["redirect_url"])
        state = WorkflowConnectionState.objects.get(connection=connection)
        self.assertEqual(state.state_values["access_token"], "oauth-access-new")
        self.assertEqual(state.state_values["refresh_token"], "oauth-refresh-new")
        self.assertEqual(state.state_values["account_id"], "acct_new")

    def test_workflow_detail_renders_scoped_connections_card(self):
        connection = WorkflowConnection.objects.create(
            environment=self.environment,
            name="Primary OpenAI",
            integration_id="openai",
            connection_type="openai.api",
        )
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("workflow_detail", args=[self.workflow.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Available credentials")
        self.assertContains(response, connection.name)
        self.assertContains(response, reverse("workflowconnection_list"))

    def test_workflow_designer_updates_definition(self):
        self.client.force_login(self.staff_user)
        connection = self._create_connection(
            environment=self.environment,
            name="Designer OpenAI",
            integration_id="openai",
            connection_type="openai.api",
            data={
                "auth_mode": "api_key",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-test-openai",
            },
        )
        updated_definition = {
            "nodes": [
                {
                    "id": "trigger-1",
                    "kind": "trigger",
                    "label": "New task",
                    "type": "core.manual_trigger",
                    "position": {"x": 32, "y": 40},
                },
                {
                    "id": "agent-1",
                    "kind": "agent",
                    "label": "Planner",
                    "type": "core.agent",
                    "config": {
                        "template": "Plan work for {{ trigger.payload.ticket_id }}",
                        "output_key": "plan",
                    },
                    "position": {"x": 320, "y": 80},
                },
                {
                    "id": "model-1",
                    "kind": "tool",
                    "label": "OpenAI chat model",
                    "type": "openai.model.chat",
                    "config": {
                        "connection_id": str(connection.pk),
                        "model": "gpt-4.1-mini",
                    },
                    "position": {"x": 320, "y": 240},
                },
                {
                    "id": "response-1",
                    "kind": "response",
                    "label": "Return plan",
                    "type": "core.response",
                    "config": {
                        "template": "Planned {{ plan }}",
                        "status": "succeeded",
                    },
                    "position": {"x": 608, "y": 80},
                },
            ],
            "edges": [
                {"id": "edge-1", "source": "trigger-1", "target": "agent-1"},
                {"id": "edge-2", "source": "agent-1", "target": "response-1"},
                {
                    "id": "edge-3",
                    "source": "model-1",
                    "sourcePort": "ai_languageModel",
                    "target": "agent-1",
                    "targetPort": "ai_languageModel",
                },
            ],
        }

        response = self.client.post(
            reverse("workflow_designer", args=[self.workflow.pk]),
            {
                "definition": json.dumps(updated_definition),
            },
        )

        self.assertRedirects(response, reverse("workflow_designer", args=[self.workflow.pk]))
        self.workflow.refresh_from_db()
        self.assertEqual(self.workflow.node_count, 4)
        self.assertEqual(self.workflow.edge_count, 3)
        self.assertEqual(self.workflow.definition["definition_version"], 2)
        self.assertEqual(self.workflow.definition["nodes"][0]["type"], "core.manual_trigger")
        self.assertEqual(self.workflow.definition["nodes"][1]["type"], "core.agent")
        self.assertEqual(self.workflow.definition["nodes"][1]["name"], "Planner")
        self.assertEqual(
            self.workflow.definition["nodes"][1]["parameters"],
            {"template": "Plan work for {{ trigger.payload.ticket_id }}", "output_key": "plan"},
        )
        self.assertEqual(self.workflow.definition["nodes"][2]["type"], "openai.model.chat")
        self.assertEqual(self.workflow.definition["nodes"][2]["name"], "OpenAI chat model")
        self.assertEqual(self.workflow.definition["nodes"][3]["type"], "core.response")
        self.assertEqual(self.workflow.definition["edges"][2]["source_port"], "ai_languageModel")
        self.assertEqual(self.workflow.definition["edges"][2]["target_port"], "ai_languageModel")

    def test_workflow_designer_save_endpoint_updates_definition(self):
        self.client.force_login(self.staff_user)
        updated_definition = {
            "nodes": [
                {
                    "id": "trigger-1",
                    "kind": "trigger",
                    "label": "New task",
                    "type": "core.manual_trigger",
                    "position": {"x": 32, "y": 40},
                },
                {
                    "id": "response-1",
                    "kind": "response",
                    "label": "Autosaved response",
                    "type": "core.response",
                    "config": {
                        "template": "Completed {{ trigger.payload.ticket_id }}",
                    },
                    "position": {"x": 320, "y": 40},
                },
            ],
            "edges": [
                {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
            ],
        }

        response = self.client.post(
            reverse("workflow_designer_save", args=[self.workflow.pk]),
            data=json.dumps({"definition": updated_definition}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["detail"], "Workflow saved.")
        self.assertEqual(payload["workflow"]["node_count"], 2)
        self.assertEqual(payload["workflow"]["edge_count"], 1)
        self.workflow.refresh_from_db()
        self.assertEqual(self.workflow.definition["definition_version"], 2)
        self.assertEqual(self.workflow.definition["nodes"][1]["name"], "Autosaved response")
        self.assertEqual(
            self.workflow.definition["nodes"][1]["parameters"],
            {"template": "Completed {{ trigger.payload.ticket_id }}"},
        )

    def test_workflow_designer_save_endpoint_rejects_unsupported_definition(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("workflow_designer_save", args=[self.workflow.pk]),
            data=json.dumps({"definition": _unsupported_definition("Unsupported task")}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("only supports v2 catalog nodes", response.json()["detail"])

    def test_workflow_designer_save_endpoint_ignores_stale_revision(self):
        self.client.force_login(self.staff_user)
        newer_definition = {
            "nodes": [
                {
                    "id": "trigger-1",
                    "kind": "trigger",
                    "label": "New task",
                    "type": "core.manual_trigger",
                    "position": {"x": 32, "y": 40},
                },
                {
                    "id": "response-1",
                    "kind": "response",
                    "label": "Newer response",
                    "type": "core.response",
                    "config": {
                        "template": "newer",
                    },
                    "position": {"x": 320, "y": 40},
                },
            ],
            "edges": [
                {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
            ],
        }
        stale_definition = {
            "nodes": [
                {
                    "id": "trigger-1",
                    "kind": "trigger",
                    "label": "New task",
                    "type": "core.manual_trigger",
                    "position": {"x": 32, "y": 40},
                },
                {
                    "id": "response-1",
                    "kind": "response",
                    "label": "Stale response",
                    "type": "core.response",
                    "config": {
                        "template": "stale",
                    },
                    "position": {"x": 320, "y": 40},
                },
            ],
            "edges": [
                {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
            ],
        }

        newer_response = self.client.post(
            reverse("workflow_designer_save", args=[self.workflow.pk]),
            data=json.dumps({"definition": newer_definition, "revision": 2}),
            content_type="application/json",
        )
        stale_response = self.client.post(
            reverse("workflow_designer_save", args=[self.workflow.pk]),
            data=json.dumps({"definition": stale_definition, "revision": 1}),
            content_type="application/json",
        )

        self.assertEqual(newer_response.status_code, 200)
        self.assertEqual(stale_response.status_code, 200)
        self.assertTrue(stale_response.json()["stale"])
        self.workflow.refresh_from_db()
        self.assertEqual(self.workflow.definition["nodes"][1]["name"], "Newer response")
        self.assertEqual(
            self.workflow.definition["nodes"][1]["parameters"],
            {"template": "newer"},
        )

    def test_workflow_designer_rejects_unsupported_definition_submission(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("workflow_designer", args=[self.workflow.pk]),
            {
                "definition": json.dumps(_unsupported_definition("Unsupported task")),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "only supports v2 catalog nodes")

    def test_workflow_designer_run_endpoint_saves_definition_and_executes_workflow(self):
        self.client.force_login(self.staff_user)
        definition = {
            "nodes": [
                {
                    "id": "trigger-1",
                    "kind": "trigger",
                    "type": "core.manual_trigger",
                    "label": "Manual",
                    "position": {"x": 32, "y": 40},
                },
                {
                    "id": "response-1",
                    "kind": "response",
                    "type": "core.response",
                    "label": "Reply",
                    "config": {
                        "template": "Completed {{ trigger.payload.ticket_id }}",
                    },
                    "position": {"x": 320, "y": 40},
                },
            ],
            "edges": [
                {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
            ],
        }

        with patch("automation.runtime.ensure_workers_for_queue"), patch(
            "automation.runtime.enqueue_workflow_run_job",
            side_effect=lambda run: run,
        ):
            response = self.client.post(
                reverse("workflow_designer_run", args=[self.workflow.pk]),
                data=json.dumps(
                    {
                        "definition": definition,
                        "input_data": {"ticket_id": "T-42"},
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.workflow.refresh_from_db()
        self.assertEqual(self.workflow.definition["definition_version"], 2)
        self.assertEqual(self.workflow.definition["nodes"][1]["name"], "Reply")
        self.assertEqual(
            self.workflow.definition["nodes"][1]["parameters"],
            {"template": "Completed {{ trigger.payload.ticket_id }}"},
        )
        self.assertEqual(payload["mode"], "workflow")
        self.assertEqual(payload["run"]["status"], "pending")
        run = WorkflowRun.objects.get(pk=payload["run"]["id"])
        execute_workflow_run(run)
        status_response = self.client.get(payload["poll_url"])
        self.assertEqual(status_response.status_code, 200)
        status_payload = status_response.json()
        self.assertEqual(status_payload["run"]["status"], "succeeded")
        self.assertIn("Completed T-42", status_payload["run"]["output_json"])

    def test_workflow_designer_run_endpoint_puts_webhook_workflow_into_listen_mode(self):
        self.client.force_login(self.staff_user)
        definition = {
            "nodes": [
                {
                    "id": "trigger-1",
                    "kind": "trigger",
                    "type": "core.webhook_trigger",
                    "label": "Webhook",
                    "config": {
                        "http_method": "POST",
                    },
                    "position": {"x": 32, "y": 40},
                },
                {
                    "id": "response-1",
                    "kind": "response",
                    "type": "core.response",
                    "label": "Reply",
                    "config": {
                        "template": "Completed {{ trigger.payload.ticket_id }}",
                    },
                    "position": {"x": 320, "y": 40},
                },
            ],
            "edges": [
                {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
            ],
        }

        with patch("automation.runtime.ensure_workers_for_queue") as ensure_workers, patch(
            "automation.runtime.enqueue_workflow_run_job"
        ) as enqueue_job:
            response = self.client.post(
                reverse("workflow_designer_run", args=[self.workflow.pk]),
                data=json.dumps(
                    {
                        "definition": definition,
                        "input_data": {"ticket_id": "T-42"},
                    }
                ),
                content_type="application/json",
            )

        ensure_workers.assert_not_called()
        enqueue_job.assert_not_called()
        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["mode"], "workflow_listen")
        self.assertEqual(payload["run"]["status"], "pending")
        self.assertEqual(payload["message"], "Listening for webhook event.")

        run = WorkflowRun.objects.get(pk=payload["run"]["id"])
        self.assertEqual(run.execution_mode, WorkflowRun.ExecutionModeChoices.WORKFLOW)
        self.assertEqual(run.target_node_id, "")
        self.assertEqual(run.trigger_mode, "manual:webhook_listen")
        self.assertEqual(run.trigger_metadata["listen_mode"], "webhook")

    def test_workflow_webhook_trigger_claims_pending_workflow_listen_run_and_executes_it(self):
        self.client.force_login(self.staff_user)
        definition = {
            "nodes": [
                {
                    "id": "trigger-1",
                    "kind": "trigger",
                    "type": "core.webhook_trigger",
                    "label": "Webhook",
                    "config": {
                        "http_method": "POST",
                    },
                    "position": {"x": 32, "y": 40},
                },
                {
                    "id": "response-1",
                    "kind": "response",
                    "type": "core.response",
                    "label": "Reply",
                    "config": {
                        "template": "Completed {{ trigger.payload.ticket_id }}",
                    },
                    "position": {"x": 320, "y": 40},
                },
            ],
            "edges": [
                {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
            ],
        }

        listen_response = self.client.post(
            reverse("workflow_designer_run", args=[self.workflow.pk]),
            data=json.dumps(
                {
                    "definition": definition,
                    "input_data": {"ticket_id": "T-42"},
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(listen_response.status_code, 202)
        listen_payload = listen_response.json()
        run = WorkflowRun.objects.get(pk=listen_payload["run"]["id"])
        self.assertEqual(run.status, WorkflowRun.StatusChoices.PENDING)
        self.assertEqual(run.target_node_id, "")
        self.workflow.refresh_from_db()

        webhook_response = self.client.post(
            self._get_public_webhook_url(self.workflow),
            data=json.dumps({"ticket_id": "INC-900"}),
            content_type="application/json",
        )

        self.assertEqual(webhook_response.status_code, 200)
        webhook_payload = webhook_response.json()
        self.assertEqual(webhook_payload["run_id"], run.pk)
        self.assertEqual(webhook_payload["status"], WorkflowRun.StatusChoices.SUCCEEDED)
        self.assertEqual(webhook_payload["output_data"]["response"], "Completed INC-900")

        run.refresh_from_db()
        self.assertEqual(run.status, WorkflowRun.StatusChoices.SUCCEEDED)
        self.assertEqual(run.trigger_metadata["trigger_node_id"], "trigger-1")
        self.assertEqual(run.output_data["response"], "Completed INC-900")

        status_response = self.client.get(listen_payload["poll_url"])
        self.assertEqual(status_response.status_code, 200)
        status_payload = status_response.json()
        self.assertEqual(status_payload["mode"], "workflow_listen")
        self.assertEqual(status_payload["run"]["status"], "succeeded")
        self.assertIn("Completed INC-900", status_payload["run"]["output_json"])

    def test_workflow_designer_run_endpoint_rejects_unsupported_definition(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("workflow_designer_run", args=[self.workflow.pk]),
            data=json.dumps(
                {
                    "definition": _unsupported_definition("Unsupported task"),
                    "input_data": {"ticket_id": "T-42"},
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("only supports v2 catalog nodes", response.json()["detail"])

    def test_workflow_delete_shows_blocked_message_when_run_history_exists(self):
        version = WorkflowVersion.objects.create(
            workflow=self.workflow,
            version=1,
            definition=self.workflow.definition,
        )
        WorkflowRun.objects.create(
            workflow=self.workflow,
            workflow_version=version,
        )
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("workflow_delete", args=[self.workflow.pk]),
            {"return_url": reverse("workflow_list")},
        )

        self.assertEqual(response.status_code, 409)
        self.assertContains(response, "Cannot delete workflow because related records still exist", status_code=409)
        self.assertContains(response, "workflow run", status_code=409)
        self.workflow.refresh_from_db()

    def test_workflow_delete_can_purge_history_from_delete_ui(self):
        version = WorkflowVersion.objects.create(
            workflow=self.workflow,
            version=1,
            definition=self.workflow.definition,
        )
        run = WorkflowRun.objects.create(
            workflow=self.workflow,
            workflow_version=version,
        )
        WorkflowStepRun.objects.create(
            run=run,
            workflow_version=version,
            sequence=1,
            node_id="trigger-1",
            node_kind="trigger",
            node_type="core.manual_trigger",
            label="Manual Trigger",
        )
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("workflow_delete", args=[self.workflow.pk]),
            {"return_url": reverse("workflow_list"), "delete_history": "on"},
        )

        self.assertRedirects(response, reverse("workflow_list"))
        self.assertFalse(Workflow.objects.filter(pk=self.workflow.pk).exists())
        self.assertFalse(WorkflowRun.objects.filter(pk=run.pk).exists())
        self.assertFalse(WorkflowStepRun.objects.filter(run=run).exists())
        self.assertFalse(WorkflowVersion.objects.filter(pk=version.pk).exists())

    def test_workflow_designer_node_run_endpoint_runs_primary_node_preview_only(self):
        self.client.force_login(self.staff_user)
        definition = {
            "nodes": [
                {
                    "id": "trigger-1",
                    "kind": "trigger",
                    "type": "core.manual_trigger",
                    "label": "Manual",
                    "position": {"x": 32, "y": 40},
                },
                {
                    "id": "tool-1",
                    "kind": "tool",
                    "type": "core.set",
                    "label": "Set value",
                    "config": {
                        "mode": "raw",
                        "output_key": "tool.output",
                        "json_output": '"Service {{ trigger.payload.service }}"',
                    },
                    "position": {"x": 320, "y": 40},
                },
                {
                    "id": "response-1",
                    "kind": "response",
                    "type": "core.response",
                    "label": "Done",
                    "config": {
                        "template": "{{ tool.output }}",
                    },
                    "position": {"x": 608, "y": 40},
                },
            ],
            "edges": [
                {"id": "edge-1", "source": "trigger-1", "target": "tool-1"},
                {"id": "edge-2", "source": "tool-1", "target": "response-1"},
            ],
        }

        with patch("automation.runtime.ensure_workers_for_queue"), patch(
            "automation.runtime.enqueue_workflow_run_job",
            side_effect=lambda run: run,
        ):
            response = self.client.post(
                reverse("workflow_designer_node_run", args=[self.workflow.pk, "tool-1"]),
                data=json.dumps(
                    {
                        "definition": definition,
                        "input_data": {"service": "payments"},
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["mode"], "node_preview")
        self.assertEqual(payload["node"]["id"], "tool-1")
        self.assertEqual(payload["run"]["status"], "pending")
        run = WorkflowRun.objects.get(pk=payload["run"]["id"])
        execute_workflow_run(run)
        status_response = self.client.get(payload["poll_url"])
        self.assertEqual(status_response.status_code, 200)
        status_payload = status_response.json()
        self.assertEqual(status_payload["run"]["status"], "succeeded")
        self.assertEqual(status_payload["run"]["step_count"], 1)
        self.assertIn("Service payments", status_payload["run"]["output_json"])

    def test_workflow_designer_node_run_endpoint_runs_auxiliary_node_preview(self):
        self.client.force_login(self.staff_user)
        connection = self._create_connection(
            environment=self.environment,
            name="Node preview OpenAI",
            integration_id="openai",
            connection_type="openai.api",
            data={
                "auth_mode": "api_key",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-test-openai",
            },
        )
        definition = {
            "nodes": [
                {
                    "id": "trigger-1",
                    "kind": "trigger",
                    "type": "core.manual_trigger",
                    "label": "Manual",
                    "position": {"x": 32, "y": 40},
                },
                {
                    "id": "agent-1",
                    "kind": "agent",
                    "type": "core.agent",
                    "label": "Draft",
                    "config": {
                        "template": "Review {{ trigger.payload.ticket_id }}",
                    },
                    "position": {"x": 320, "y": 40},
                },
                {
                    "id": "model-1",
                    "kind": "tool",
                    "type": "openai.model.chat",
                    "label": "OpenAI chat model",
                    "config": {
                        "connection_id": str(connection.pk),
                        "model": "gpt-4.1-mini",
                    },
                    "position": {"x": 320, "y": 240},
                },
                {
                    "id": "response-1",
                    "kind": "response",
                    "type": "core.response",
                    "label": "Done",
                    "config": {
                        "template": "Completed",
                    },
                    "position": {"x": 608, "y": 40},
                },
            ],
            "edges": [
                {"id": "edge-1", "source": "trigger-1", "target": "agent-1"},
                {"id": "edge-2", "source": "agent-1", "target": "response-1"},
                {
                    "id": "edge-3",
                    "source": "model-1",
                    "sourcePort": "ai_languageModel",
                    "target": "agent-1",
                    "targetPort": "ai_languageModel",
                },
            ],
        }

        with patch("automation.runtime.ensure_workers_for_queue"), patch(
            "automation.runtime.enqueue_workflow_run_job",
            side_effect=lambda run: run,
        ):
            response = self.client.post(
                reverse("workflow_designer_node_run", args=[self.workflow.pk, "model-1"]),
                data=json.dumps(
                    {
                        "definition": definition,
                        "input_data": {"ticket_id": "T-42"},
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["mode"], "node_preview")
        self.assertEqual(payload["node"]["id"], "model-1")
        self.assertEqual(payload["run"]["status"], "pending")
        run = WorkflowRun.objects.get(pk=payload["run"]["id"])
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai"}, clear=False):
            execute_workflow_run(run)
        status_response = self.client.get(payload["poll_url"])
        self.assertEqual(status_response.status_code, 200)
        status_payload = status_response.json()
        self.assertEqual(status_payload["run"]["status"], "succeeded")
        self.assertEqual(status_payload["run"]["step_count"], 1)
        self.assertIn("gpt-4.1-mini", status_payload["run"]["output_json"])

    def test_workflow_designer_node_run_endpoint_puts_webhook_trigger_into_listen_mode(self):
        self.client.force_login(self.staff_user)
        definition = {
            "nodes": [
                {
                    "id": "trigger-1",
                    "kind": "trigger",
                    "type": "core.webhook_trigger",
                    "label": "Webhook",
                    "config": {
                        "http_method": "POST",
                        "authentication": "none",
                        "response_mode": "immediately",
                    },
                    "position": {"x": 32, "y": 40},
                },
                {
                    "id": "response-1",
                    "kind": "response",
                    "type": "core.response",
                    "label": "Done",
                    "config": {
                        "template": "ok",
                    },
                    "position": {"x": 320, "y": 40},
                },
            ],
            "edges": [
                {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
            ],
        }

        with patch("automation.runtime.ensure_workers_for_queue") as ensure_workers, patch(
            "automation.runtime.enqueue_workflow_run_job"
        ) as enqueue_job:
            response = self.client.post(
                reverse("workflow_designer_node_run", args=[self.workflow.pk, "trigger-1"]),
                data=json.dumps({"definition": definition}),
                content_type="application/json",
            )

        ensure_workers.assert_not_called()
        enqueue_job.assert_not_called()
        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["mode"], "node_listen")
        self.assertEqual(payload["node"]["id"], "trigger-1")
        self.assertEqual(payload["run"]["status"], "pending")
        self.assertEqual(payload["message"], "Listening for webhook event.")

        run = WorkflowRun.objects.get(pk=payload["run"]["id"])
        self.assertEqual(run.execution_mode, WorkflowRun.ExecutionModeChoices.WORKFLOW)
        self.assertEqual(run.target_node_id, "trigger-1")
        self.assertEqual(run.trigger_mode, "manual:webhook_listen")
        self.assertEqual(run.trigger_metadata["listen_mode"], "webhook")

    def test_workflow_webhook_trigger_claims_pending_listen_run_and_executes_it(self):
        self.client.force_login(self.staff_user)

        definition = {
            "nodes": [
                {
                    "id": "trigger-1",
                    "kind": "trigger",
                    "type": "core.webhook_trigger",
                    "label": "Webhook",
                    "config": {
                        "http_method": "POST",
                        "authentication": "none",
                        "response_mode": "immediately",
                    },
                    "position": {"x": 32, "y": 40},
                },
                {
                    "id": "response-1",
                    "kind": "response",
                    "type": "core.response",
                    "label": "Done",
                    "config": {
                        "template": "ticket:{{ trigger.payload.ticket_id }}",
                    },
                    "position": {"x": 320, "y": 40},
                },
            ],
            "edges": [
                {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
            ],
        }

        listen_response = self.client.post(
            reverse("workflow_designer_node_run", args=[self.workflow.pk, "trigger-1"]),
            data=json.dumps({"definition": definition}),
            content_type="application/json",
        )

        self.assertEqual(listen_response.status_code, 202)
        listen_payload = listen_response.json()
        run = WorkflowRun.objects.get(pk=listen_payload["run"]["id"])
        self.assertEqual(run.status, WorkflowRun.StatusChoices.PENDING)
        self.workflow.refresh_from_db()

        webhook_response = self.client.post(
            self._get_public_webhook_url(self.workflow),
            data=json.dumps({"ticket_id": "INC-123"}),
            content_type="application/json",
        )

        self.assertEqual(webhook_response.status_code, 200)
        webhook_payload = webhook_response.json()
        self.assertEqual(webhook_payload["run_id"], run.pk)
        self.assertEqual(webhook_payload["status"], WorkflowRun.StatusChoices.SUCCEEDED)
        self.assertEqual(webhook_payload["output_data"]["response"], "ticket:INC-123")

        run.refresh_from_db()
        self.assertEqual(run.status, WorkflowRun.StatusChoices.SUCCEEDED)
        self.assertEqual(run.execution_mode, WorkflowRun.ExecutionModeChoices.WORKFLOW)
        self.assertEqual(run.target_node_id, "trigger-1")
        self.assertEqual(run.trigger_metadata["listen_mode"], "webhook")
        self.assertEqual(run.trigger_metadata["trigger_node_id"], "trigger-1")
        self.assertEqual(run.output_data["response"], "ticket:INC-123")

        status_response = self.client.get(listen_payload["poll_url"])
        self.assertEqual(status_response.status_code, 200)
        status_payload = status_response.json()
        self.assertEqual(status_payload["mode"], "node_listen")
        self.assertEqual(status_payload["node"]["id"], "trigger-1")
        self.assertEqual(status_payload["run"]["status"], "succeeded")
        self.assertIn("ticket:INC-123", status_payload["run"]["output_json"])

    def test_workflow_detail_post_executes_runtime_and_persists_run(self):
        self.workflow.definition = {
            "nodes": [
                {
                    "id": "trigger-1",
                    "kind": "trigger",
                    "type": "core.manual_trigger",
                    "label": "Manual",
                    "position": {"x": 32, "y": 40},
                },
                {
                    "id": "agent-1",
                    "kind": "agent",
                    "type": "core.agent",
                    "label": "Draft",
                    "config": {
                        "template": "Review {{ trigger.payload.ticket_id }}",
                    },
                    "position": {"x": 320, "y": 40},
                },
                {
                    "id": "model-1",
                    "kind": "tool",
                    "type": "openai.model.chat",
                    "label": "OpenAI chat model",
                    "config": {
                        "base_url": "https://api.openai.com/v1",
                        "model": "gpt-4.1-mini",
                        "secret_name": "OPENAI_API_KEY",
                    },
                    "position": {"x": 320, "y": 240},
                },
                {
                    "id": "response-1",
                    "kind": "response",
                    "type": "core.response",
                    "label": "Done",
                    "config": {
                        "template": "Completed {{ llm.response.text }}",
                    },
                    "position": {"x": 608, "y": 40},
                },
            ],
            "edges": [
                {"id": "edge-1", "source": "trigger-1", "target": "agent-1"},
                {"id": "edge-2", "source": "agent-1", "target": "response-1"},
                {
                    "id": "edge-3",
                    "source": "model-1",
                    "sourcePort": "ai_languageModel",
                    "target": "agent-1",
                    "targetPort": "ai_languageModel",
                },
            ],
        }
        self.workflow.save(update_fields=("definition",))
        self._attach_openai_connection(self.workflow)
        self.client.force_login(self.staff_user)

        def fake_urlopen(request, timeout=20):
            self.assertEqual(timeout, 20)
            body = json.loads(request.data.decode("utf-8"))
            self.assertEqual(body["messages"][0]["content"], "Review T-42")
            return _FakeJsonResponse(
                {
                    "id": "chatcmpl-views-1",
                    "model": "gpt-4.1-mini",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "content": "Review T-42",
                            },
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
                }
            )

        with patch("automation.runtime.ensure_workers_for_queue"), patch(
            "automation.runtime.enqueue_workflow_run_job",
            side_effect=lambda run: run,
        ):
            response = self.client.post(
                reverse("workflow_detail", args=[self.workflow.pk]),
                {
                    "input_data": json.dumps({"ticket_id": "T-42"}),
                },
            )

        self.assertRedirects(response, reverse("workflow_detail", args=[self.workflow.pk]))
        run = WorkflowRun.objects.get(workflow=self.workflow)
        self.assertEqual(run.status, WorkflowRun.StatusChoices.PENDING)
        self.assertEqual(run.execution_mode, WorkflowRun.ExecutionModeChoices.WORKFLOW)

    def test_home_dashboard_includes_workflow_automation_summary_for_staff(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        stats_by_title = {section["title"]: section for section in response.context["stats"]}
        self.assertIn("Workflow Automation", stats_by_title)
        automation_items = {item["label"]: item for item in stats_by_title["Workflow Automation"]["items"]}
        self.assertEqual(automation_items["Workflows"]["count"], 2)

    def test_home_dashboard_scopes_workflow_automation_summary_for_members(self):
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        stats_by_title = {section["title"]: section for section in response.context["stats"]}
        self.assertIn("Workflow Automation", stats_by_title)
        automation_items = {item["label"]: item for item in stats_by_title["Workflow Automation"]["items"]}
        self.assertEqual(automation_items["Workflows"]["count"], 1)
        self.assertContains(response, "Workflows")

    def test_workflow_webhook_trigger_accepts_github_payload_with_valid_signature(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="GitHub webhook",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "github.trigger.webhook",
                        "label": "GitHub",
                        "config": {
                            "connection_id": "",
                            "owner": "acme",
                            "repository": "platform",
                            "events": ["push"],
                        },
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {
                            "template": "{{ trigger.meta.event }}:{{ trigger.payload.repository.full_name }}",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
                ],
            },
        )
        connection = self._create_connection(
            environment=self.environment,
            name="Primary GitHub",
            integration_id="github",
            connection_type="github.oauth2",
            data={"webhook_secret": "github-secret"},
        )
        workflow.definition["nodes"][0]["connections"] = {"connection_id": str(connection.pk)}
        workflow.save(update_fields=("definition",))
        body = json.dumps({"repository": {"full_name": "acme/platform"}}).encode("utf-8")

        signature = "sha256=" + hmac.new(
            b"github-secret",
            body,
            hashlib.sha256,
        ).hexdigest()
        _, _, run = self._queue_workflow_request(
            lambda: self.client.post(
                reverse("workflow_webhook_trigger_legacy", args=[workflow.pk]),
                data=body,
                content_type="application/json",
                HTTP_X_HUB_SIGNATURE_256=signature,
                HTTP_X_GITHUB_EVENT="push",
                HTTP_X_GITHUB_DELIVERY="delivery-1",
            )
        )

        execute_workflow_run(run)
        run.refresh_from_db()
        self.assertEqual(run.status, WorkflowRun.StatusChoices.SUCCEEDED)
        self.assertEqual(run.output_data["response"], "push:acme/platform")
        self.assertEqual(run.context_data["trigger"]["meta"]["event"], "push")

    def test_workflow_webhook_trigger_accepts_github_payload_without_credential(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="GitHub webhook unsigned",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "github.trigger.webhook",
                        "label": "GitHub",
                        "config": {
                            "owner": "acme",
                            "repository": "platform",
                            "events": ["push"],
                        },
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {
                            "template": "{{ trigger.meta.event }}:{{ trigger.payload.repository.full_name }}",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
                ],
            },
        )
        body = json.dumps({"repository": {"full_name": "acme/platform"}}).encode("utf-8")

        _, _, run = self._queue_workflow_request(
            lambda: self.client.post(
                reverse("workflow_webhook_trigger_legacy", args=[workflow.pk]),
                data=body,
                content_type="application/json",
                HTTP_X_GITHUB_EVENT="push",
                HTTP_X_GITHUB_DELIVERY="delivery-unsigned",
            )
        )

        execute_workflow_run(run)
        run.refresh_from_db()
        self.assertEqual(run.status, WorkflowRun.StatusChoices.SUCCEEDED)
        self.assertEqual(run.output_data["response"], "push:acme/platform")
        self.assertEqual(run.context_data["trigger"]["meta"]["event"], "push")
        self.assertNotIn("connection", run.context_data["trigger"]["meta"])
        self.assertNotIn("secret", run.context_data["trigger"]["meta"])

    def test_workflow_webhook_trigger_accepts_public_github_payload_without_credential(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="GitHub webhook unsigned public",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "github.trigger.webhook",
                        "label": "GitHub",
                        "config": {
                            "path": "github/public/path",
                            "owner": "acme",
                            "repository": "platform",
                            "events": ["push"],
                        },
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {
                            "template": "{{ trigger.meta.event }}:{{ trigger.payload.repository.full_name }}",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
                ],
            },
        )
        body = json.dumps({"repository": {"full_name": "acme/platform"}}).encode("utf-8")

        _, _, run = self._queue_workflow_request(
            lambda: self.client.post(
                reverse("workflow_webhook_trigger_public", args=["github/public/path"]),
                data=body,
                content_type="application/json",
                HTTP_X_GITHUB_EVENT="push",
            )
        )

        execute_workflow_run(run)
        run.refresh_from_db()
        self.assertEqual(run.status, WorkflowRun.StatusChoices.SUCCEEDED)
        self.assertEqual(run.output_data["response"], "push:acme/platform")
        self.assertEqual(run.context_data["trigger"]["meta"]["event"], "push")

    def test_workflow_webhook_trigger_accepts_github_payload_with_connection_without_secret(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="GitHub webhook unsigned connection",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "github.trigger.webhook",
                        "label": "GitHub",
                        "config": {
                            "connection_id": "",
                            "owner": "acme",
                            "repository": "platform",
                            "events": ["push"],
                        },
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {
                            "template": "{{ trigger.meta.event }}:{{ trigger.payload.repository.full_name }}",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
                ],
            },
        )
        connection = self._create_connection(
            environment=self.environment,
            name="GitHub without secret",
            integration_id="github",
            connection_type="github.oauth2",
        )
        workflow.definition["nodes"][0]["connections"] = {"connection_id": str(connection.pk)}
        workflow.save(update_fields=("definition",))
        body = json.dumps({"repository": {"full_name": "acme/platform"}}).encode("utf-8")

        _, _, run = self._queue_workflow_request(
            lambda: self.client.post(
                reverse("workflow_webhook_trigger_legacy", args=[workflow.pk]),
                data=body,
                content_type="application/json",
                HTTP_X_GITHUB_EVENT="push",
            )
        )

        execute_workflow_run(run)
        run.refresh_from_db()
        self.assertEqual(run.status, WorkflowRun.StatusChoices.SUCCEEDED)
        self.assertEqual(run.output_data["response"], "push:acme/platform")
        self.assertEqual(run.context_data["trigger"]["meta"]["connection"]["type"], "github.oauth2")
        self.assertNotIn("secret", run.context_data["trigger"]["meta"])

    def test_workflow_webhook_trigger_accepts_generic_payload(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Generic webhook",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "core.webhook_trigger",
                        "label": "Webhook",
                        "config": {
                            "http_method": "POST",
                        },
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {
                            "template": "{{ trigger.payload.ticket_id }}:{{ trigger.meta.method }}",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
                ],
            },
            enabled=True,
        )

        _, _, run = self._queue_workflow_request(
            lambda: self.client.post(
                self._get_public_webhook_url(workflow),
                data=json.dumps({"ticket_id": "INC-123"}),
                content_type="application/json",
            )
        )

        execute_workflow_run(run)
        run.refresh_from_db()
        self.assertEqual(run.status, WorkflowRun.StatusChoices.SUCCEEDED)
        self.assertEqual(run.output_data["response"], "INC-123:POST")

    def test_workflow_webhook_trigger_accepts_generic_payload_with_header_auth_connection(self):
        connection = self._create_connection(
            environment=self.environment,
            name="Generic webhook auth",
            integration_id="webhook",
            connection_type="webhook.header_auth",
            data={
                "name": "X-Webhook-Secret",
                "value": "shared-secret",
            },
        )
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Generic webhook auth",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "core.webhook_trigger",
                        "label": "Webhook",
                        "config": {
                            "http_method": "POST",
                            "authentication": "headerAuth",
                            "connection_id": str(connection.pk),
                        },
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {
                            "template": "{{ trigger.payload.ticket_id }}:{{ trigger.meta.authentication }}",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
                ],
            },
            enabled=True,
        )

        _, _, run = self._queue_workflow_request(
            lambda: self.client.post(
                self._get_public_webhook_url(workflow),
                data=json.dumps({"ticket_id": "INC-123"}),
                content_type="application/json",
                HTTP_X_WEBHOOK_SECRET="shared-secret",
            )
        )

        execute_workflow_run(run)
        run.refresh_from_db()
        self.assertEqual(run.status, WorkflowRun.StatusChoices.SUCCEEDED)
        self.assertEqual(run.output_data["response"], "INC-123:headerAuth")
        self.assertEqual(run.context_data["trigger"]["meta"]["connection"]["type"], "webhook.header_auth")

    def test_workflow_webhook_trigger_rejects_generic_payload_with_invalid_header_auth(self):
        connection = self._create_connection(
            environment=self.environment,
            name="Generic webhook auth invalid",
            integration_id="webhook",
            connection_type="webhook.header_auth",
            data={
                "name": "X-Webhook-Secret",
                "value": "shared-secret",
            },
        )
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Generic webhook auth invalid",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "core.webhook_trigger",
                        "label": "Webhook",
                        "config": {
                            "http_method": "POST",
                            "authentication": "headerAuth",
                            "connection_id": str(connection.pk),
                        },
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
                ],
            },
            enabled=True,
        )

        response = self.client.post(
            self._get_public_webhook_url(workflow),
            data=json.dumps({"ticket_id": "INC-123"}),
            content_type="application/json",
            HTTP_X_WEBHOOK_SECRET="wrong-secret",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("header-auth validation failed", response.json()["detail"])

    def test_workflow_webhook_trigger_accepts_generic_payload_with_basic_auth_connection(self):
        connection = self._create_connection(
            environment=self.environment,
            name="Generic webhook basic auth",
            integration_id="webhook",
            connection_type="webhook.basic_auth",
            data={
                "username": "operator",
                "password": "secret-password",
            },
        )
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Generic webhook basic auth",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "core.webhook_trigger",
                        "label": "Webhook",
                        "config": {
                            "http_method": "POST",
                            "authentication": "basicAuth",
                            "basic_auth_connection_id": str(connection.pk),
                        },
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {
                            "template": "{{ trigger.payload.ticket_id }}:{{ trigger.meta.authentication }}",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
                ],
            },
            enabled=True,
        )

        basic_token = base64.b64encode(b"operator:secret-password").decode("ascii")
        _, _, run = self._queue_workflow_request(
            lambda: self.client.post(
                self._get_public_webhook_url(workflow),
                data=json.dumps({"ticket_id": "INC-123"}),
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Basic {basic_token}",
            )
        )

        execute_workflow_run(run)
        run.refresh_from_db()
        self.assertEqual(run.status, WorkflowRun.StatusChoices.SUCCEEDED)
        self.assertEqual(run.output_data["response"], "INC-123:basicAuth")
        self.assertEqual(run.context_data["trigger"]["meta"]["connection"]["type"], "webhook.basic_auth")

    def test_workflow_webhook_trigger_accepts_generic_payload_with_jwt_auth_connection(self):
        connection = self._create_connection(
            environment=self.environment,
            name="Generic webhook jwt auth",
            integration_id="webhook",
            connection_type="webhook.jwt_auth",
            data={
                "key_type": "passphrase",
                "secret": "jwt-secret-with-at-least-32-bytes",
                "algorithm": "HS256",
            },
        )
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Generic webhook jwt auth",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "core.webhook_trigger",
                        "label": "Webhook",
                        "config": {
                            "http_method": "POST",
                            "authentication": "jwtAuth",
                            "jwt_auth_connection_id": str(connection.pk),
                        },
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {
                            "template": "{{ trigger.payload.ticket_id }}:{{ trigger.meta.jwt_payload.sub }}",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
                ],
            },
            enabled=True,
        )

        token = jwt.encode(
            {"sub": "svc-webhook"},
            "jwt-secret-with-at-least-32-bytes",
            algorithm="HS256",
        )
        _, _, run = self._queue_workflow_request(
            lambda: self.client.post(
                self._get_public_webhook_url(workflow),
                data=json.dumps({"ticket_id": "INC-123"}),
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {token}",
            )
        )

        execute_workflow_run(run)
        run.refresh_from_db()
        self.assertEqual(run.status, WorkflowRun.StatusChoices.SUCCEEDED)
        self.assertEqual(run.output_data["response"], "INC-123:svc-webhook")
        self.assertEqual(run.context_data["trigger"]["meta"]["connection"]["type"], "webhook.jwt_auth")

    def test_workflow_webhook_trigger_accepts_legacy_header_secret_auth_configuration(self):
        connection = self._create_connection(
            environment=self.environment,
            name="Generic webhook auth legacy",
            integration_id="webhook",
            connection_type="webhook.shared_secret",
            data={
                "header_name": "X-Webhook-Secret",
                "secret_value": "shared-secret",
            },
        )
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Generic webhook auth legacy",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "core.webhook_trigger",
                        "label": "Webhook",
                        "config": {
                            "http_method": "POST",
                            "authentication": "header_secret",
                            "connection_id": str(connection.pk),
                        },
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {
                            "template": "{{ trigger.meta.authentication }}",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
                ],
            },
            enabled=True,
        )

        _, _, run = self._queue_workflow_request(
            lambda: self.client.post(
                self._get_public_webhook_url(workflow),
                data=json.dumps({"ticket_id": "INC-123"}),
                content_type="application/json",
                HTTP_X_WEBHOOK_SECRET="shared-secret",
            )
        )

        execute_workflow_run(run)
        run.refresh_from_db()
        self.assertEqual(run.status, WorkflowRun.StatusChoices.SUCCEEDED)
        self.assertEqual(run.output_data["response"], "headerAuth")

    def test_workflow_webhook_trigger_accepts_generic_payload_on_configured_path(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Generic webhook path",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "core.webhook_trigger",
                        "label": "Webhook",
                        "config": {
                            "http_method": "POST",
                            "path": "orders/new",
                        },
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {
                            "template": "{{ trigger.meta.webhook_path }}",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
                ],
            },
            enabled=True,
        )

        _, _, run = self._queue_workflow_request(
            lambda: self.client.post(
                reverse("workflow_webhook_trigger_public", args=["orders/new"]),
                data=json.dumps({"ticket_id": "INC-123"}),
                content_type="application/json",
            )
        )

        execute_workflow_run(run)
        run.refresh_from_db()
        self.assertEqual(run.status, WorkflowRun.StatusChoices.SUCCEEDED)
        self.assertEqual(run.output_data["response"], "orders/new")

    def test_workflow_webhook_trigger_rejects_request_when_path_does_not_match(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Generic webhook wrong path",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "core.webhook_trigger",
                        "label": "Webhook",
                        "config": {
                            "http_method": "POST",
                            "path": "orders/new",
                        },
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {
                            "template": "ok",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
                ],
            },
            enabled=True,
        )

        response = self.client.post(
            reverse("workflow_webhook_trigger_public", args=["orders/old"]),
            data=json.dumps({"ticket_id": "INC-123"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Workflow not found.")

    def test_workflow_webhook_trigger_accepts_public_path_without_trailing_slash(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Generic webhook without trailing slash",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "core.webhook_trigger",
                        "label": "Webhook",
                        "config": {
                            "http_method": "POST",
                            "path": "orders/no-slash",
                        },
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {
                            "template": "{{ trigger.meta.webhook_path }}",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
                ],
            },
            enabled=True,
        )

        _, _, run = self._queue_workflow_request(
            lambda: self.client.post(
                reverse("workflow_webhook_trigger_public", args=["orders/no-slash"]).rstrip("/"),
                data=json.dumps({"ticket_id": "INC-123"}),
                content_type="application/json",
            )
        )

        execute_workflow_run(run)
        run.refresh_from_db()
        self.assertEqual(run.status, WorkflowRun.StatusChoices.SUCCEEDED)
        self.assertEqual(run.output_data["response"], "orders/no-slash")

    def test_workflow_webhook_trigger_rejects_public_path_with_trailing_slash(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Generic webhook with trailing slash",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "core.webhook_trigger",
                        "label": "Webhook",
                        "config": {
                            "http_method": "POST",
                            "path": "orders/with-slash",
                        },
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {
                            "template": "{{ trigger.meta.webhook_path }}",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
                ],
            },
            enabled=True,
        )

        response = self.client.post(
            f'{reverse("workflow_webhook_trigger_public", args=["orders/with-slash"])}/',
            data=json.dumps({"ticket_id": "INC-123"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)

    def test_workflow_webhook_trigger_rejects_generic_method_mismatch(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Generic webhook method mismatch",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "core.webhook_trigger",
                        "label": "Webhook",
                        "config": {
                            "http_method": "PUT",
                        },
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
                ],
            },
            enabled=True,
        )

        response = self.client.post(
            self._get_public_webhook_url(workflow),
            data=json.dumps({"status": "wrong-method"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('does not match configured method "PUT"', response.json()["detail"])

    def test_workflow_webhook_trigger_supports_all_generic_http_methods(self):
        for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
            workflow = Workflow.objects.create(
                environment=self.environment,
                name=f"Generic webhook {method}",
                definition={
                    "nodes": [
                        {
                            "id": "trigger-1",
                            "kind": "trigger",
                            "type": "core.webhook_trigger",
                            "label": "Webhook",
                            "config": {
                                "http_method": method,
                            },
                            "position": {"x": 32, "y": 40},
                        },
                        {
                            "id": "response-1",
                            "kind": "response",
                            "type": "core.response",
                            "label": "Done",
                            "config": {
                                "template": "{{ trigger.meta.method }}",
                            },
                            "position": {"x": 320, "y": 40},
                        },
                    ],
                    "edges": [
                        {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
                    ],
                },
                enabled=True,
            )

            request_path = self._get_public_webhook_url(workflow)
            if method == "GET":
                _, _, run = self._queue_workflow_request(
                    lambda: self.client.get(request_path)
                )
            elif method == "POST":
                _, _, run = self._queue_workflow_request(
                    lambda: self.client.post(
                        request_path,
                        data=json.dumps({"ticket_id": "INC-123"}),
                        content_type="application/json",
                    )
                )
            elif method == "PUT":
                _, _, run = self._queue_workflow_request(
                    lambda: self.client.put(
                        request_path,
                        data=json.dumps({"ticket_id": "INC-123"}),
                        content_type="application/json",
                    )
                )
            elif method == "PATCH":
                _, _, run = self._queue_workflow_request(
                    lambda: self.client.patch(
                        request_path,
                        data=json.dumps({"ticket_id": "INC-123"}),
                        content_type="application/json",
                    )
                )
            else:
                _, _, run = self._queue_workflow_request(
                    lambda: self.client.delete(
                        request_path,
                        data=json.dumps({"ticket_id": "INC-123"}),
                        content_type="application/json",
                    )
                )

            execute_workflow_run(run)
            run.refresh_from_db()
            self.assertEqual(run.status, WorkflowRun.StatusChoices.SUCCEEDED)
            self.assertEqual(run.output_data["response"], method)

    def test_workflow_webhook_trigger_matches_correct_trigger_when_workflow_has_multiple_webhooks(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Multiple webhook triggers",
            definition={
                "nodes": [
                    {
                        "id": "trigger-post",
                        "kind": "trigger",
                        "type": "core.webhook_trigger",
                        "label": "Webhook POST",
                        "config": {
                            "http_method": "POST",
                            "authentication": "none",
                            "response_mode": "immediately",
                        },
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "trigger-get",
                        "kind": "trigger",
                        "type": "core.webhook_trigger",
                        "label": "Webhook GET",
                        "config": {
                            "http_method": "GET",
                            "authentication": "none",
                            "response_mode": "immediately",
                        },
                        "position": {"x": 32, "y": 180},
                    },
                    {
                        "id": "response-post",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done POST",
                        "config": {
                            "template": "post:{{ trigger.meta.method }}",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-get",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done GET",
                        "config": {
                            "template": "get:{{ trigger.meta.method }}",
                        },
                        "position": {"x": 320, "y": 180},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-post", "target": "response-post"},
                    {"id": "edge-2", "source": "trigger-get", "target": "response-get"},
                ],
            },
            enabled=True,
        )

        _, _, run = self._queue_workflow_request(
            lambda: self.client.get(self._get_public_webhook_url(workflow, node_id="trigger-get"))
        )

        execute_workflow_run(run)
        run.refresh_from_db()
        self.assertEqual(run.status, WorkflowRun.StatusChoices.SUCCEEDED)
        self.assertEqual(run.output_data["response"], "get:GET")
        self.assertEqual(run.trigger_metadata["trigger_node_id"], "trigger-get")

    def test_workflow_webhook_trigger_matches_correct_trigger_when_paths_differ(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Multiple webhook paths",
            definition={
                "nodes": [
                    {
                        "id": "trigger-orders",
                        "kind": "trigger",
                        "type": "core.webhook_trigger",
                        "label": "Webhook Orders",
                        "config": {
                            "http_method": "POST",
                            "path": "orders/new",
                        },
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "trigger-shipments",
                        "kind": "trigger",
                        "type": "core.webhook_trigger",
                        "label": "Webhook Shipments",
                        "config": {
                            "http_method": "POST",
                            "path": "shipments/new",
                        },
                        "position": {"x": 32, "y": 180},
                    },
                    {
                        "id": "response-orders",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done Orders",
                        "config": {
                            "template": "orders:{{ trigger.meta.webhook_path }}",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-shipments",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done Shipments",
                        "config": {
                            "template": "shipments:{{ trigger.meta.webhook_path }}",
                        },
                        "position": {"x": 320, "y": 180},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-orders", "target": "response-orders"},
                    {"id": "edge-2", "source": "trigger-shipments", "target": "response-shipments"},
                ],
            },
            enabled=True,
        )

        _, _, run = self._queue_workflow_request(
            lambda: self.client.post(
                reverse("workflow_webhook_trigger_public", args=["shipments/new"]),
                data=json.dumps({"ticket_id": "INC-123"}),
                content_type="application/json",
            )
        )

        execute_workflow_run(run)
        run.refresh_from_db()
        self.assertEqual(run.status, WorkflowRun.StatusChoices.SUCCEEDED)
        self.assertEqual(run.output_data["response"], "shipments:shipments/new")
        self.assertEqual(run.trigger_metadata["trigger_node_id"], "trigger-shipments")

    def test_workflow_webhook_trigger_accepts_v2_github_payload_with_valid_signature(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="GitHub webhook v2",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "github.trigger.webhook",
                        "label": "GitHub",
                        "config": {
                            "connection_id": "",
                            "owner": "acme",
                            "repository": "platform",
                            "events": ["push"],
                        },
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {
                            "template": "{{ trigger.meta.event }}:{{ trigger.payload.repository.full_name }}",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
                ],
            },
        )
        connection = self._create_connection(
            environment=self.environment,
            name="Primary GitHub",
            integration_id="github",
            connection_type="github.oauth2",
            data={"webhook_secret": "github-secret"},
        )
        workflow.definition["nodes"][0]["connections"] = {"connection_id": str(connection.pk)}
        workflow.save(update_fields=("definition",))
        body = json.dumps({"repository": {"full_name": "acme/platform"}}).encode("utf-8")

        signature = "sha256=" + hmac.new(
            b"github-secret",
            body,
            hashlib.sha256,
        ).hexdigest()
        _, _, run = self._queue_workflow_request(
            lambda: self.client.post(
                reverse("workflow_webhook_trigger_legacy", args=[workflow.pk]),
                data=body,
                content_type="application/json",
                HTTP_X_HUB_SIGNATURE_256=signature,
                HTTP_X_GITHUB_EVENT="push",
                HTTP_X_GITHUB_DELIVERY="delivery-1",
            )
        )

        execute_workflow_run(run)
        run.refresh_from_db()
        self.assertEqual(run.status, WorkflowRun.StatusChoices.SUCCEEDED)
        self.assertEqual(run.output_data["response"], "push:acme/platform")
        self.assertEqual(run.context_data["trigger"]["meta"]["event"], "push")

    def test_workflow_webhook_trigger_resolves_bound_secret_for_signature_validation(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="GitHub webhook grouped secret",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "github.trigger.webhook",
                        "label": "GitHub",
                        "config": {
                            "connection_id": "",
                            "owner": "acme",
                            "repository": "platform",
                            "events": ["push"],
                        },
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {
                            "template": "{{ trigger.meta.event }}:{{ trigger.payload.repository.full_name }}",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
                ],
            },
        )
        connection = self._create_connection(
            environment=self.environment,
            name="Primary GitHub",
            integration_id="github",
            connection_type="github.oauth2",
            data={"webhook_secret": "github-secret"},
        )
        workflow.definition["nodes"][0]["connections"] = {"connection_id": str(connection.pk)}
        workflow.save(update_fields=("definition",))
        body = json.dumps({"repository": {"full_name": "acme/platform"}}).encode("utf-8")

        signature = "sha256=" + hmac.new(
            b"github-secret",
            body,
            hashlib.sha256,
        ).hexdigest()
        _, _, run = self._queue_workflow_request(
            lambda: self.client.post(
                reverse("workflow_webhook_trigger_legacy", args=[workflow.pk]),
                data=body,
                content_type="application/json",
                HTTP_X_HUB_SIGNATURE_256=signature,
                HTTP_X_GITHUB_EVENT="push",
            )
        )

        execute_workflow_run(run)
        run.refresh_from_db()
        self.assertEqual(run.status, WorkflowRun.StatusChoices.SUCCEEDED)
        self.assertEqual(run.output_data["response"], "push:acme/platform")

    def test_workflow_webhook_trigger_accepts_typed_connection_secret_field(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="GitHub webhook typed connection",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "github.trigger.webhook",
                        "label": "GitHub",
                        "config": {
                            "connection_id": "",
                            "owner": "acme",
                            "repository": "platform",
                            "events": ["push"],
                        },
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {
                            "template": "{{ trigger.meta.event }}:{{ trigger.payload.repository.full_name }}",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
                ],
            },
        )
        connection = self._create_connection(
            environment=self.environment,
            name="Typed GitHub",
            integration_id="github",
            connection_type="github.oauth2",
            data={"webhook_secret": "github-secret"},
        )
        workflow.definition["nodes"][0]["connections"] = {"connection_id": str(connection.pk)}
        workflow.save(update_fields=("definition",))
        body = json.dumps({"repository": {"full_name": "acme/platform"}}).encode("utf-8")

        signature = "sha256=" + hmac.new(
            b"github-secret",
            body,
            hashlib.sha256,
        ).hexdigest()
        _, _, run = self._queue_workflow_request(
            lambda: self.client.post(
                reverse("workflow_webhook_trigger_legacy", args=[workflow.pk]),
                data=body,
                content_type="application/json",
                HTTP_X_HUB_SIGNATURE_256=signature,
                HTTP_X_GITHUB_EVENT="push",
            )
        )

        execute_workflow_run(run)
        run.refresh_from_db()
        self.assertEqual(run.status, WorkflowRun.StatusChoices.SUCCEEDED)
        self.assertEqual(run.output_data["response"], "push:acme/platform")

    def test_workflow_webhook_trigger_rejects_invalid_github_signature(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="GitHub webhook invalid",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "github.trigger.webhook",
                        "label": "GitHub",
                        "config": {
                            "connection_id": "",
                            "owner": "acme",
                            "repository": "platform",
                            "events": ["push"],
                        },
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
                ],
            },
        )
        connection = self._create_connection(
            environment=self.environment,
            name="Primary GitHub",
            integration_id="github",
            connection_type="github.oauth2",
            data={"webhook_secret": "github-secret"},
        )
        workflow.definition["nodes"][0]["connections"] = {"connection_id": str(connection.pk)}
        workflow.save(update_fields=("definition",))

        response = self.client.post(
            reverse("workflow_webhook_trigger_legacy", args=[workflow.pk]),
            data=json.dumps({"zen": "fail"}),
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256="sha256=bad",
            HTTP_X_GITHUB_EVENT="push",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("signature validation failed", response.json()["detail"].lower())
