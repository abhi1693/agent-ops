import hashlib
import hmac
import json
import os
from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from automation.models import Workflow, WorkflowConnection, WorkflowRun, WorkflowStepRun, WorkflowVersion
from automation.models import Secret, SecretGroup
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
                "type": "n8n-nodes-base.manualTrigger",
                "label": label,
                "position": {"x": 48, "y": 56},
            },
            {
                "id": "set-1",
                "kind": "tool",
                "type": "n8n-nodes-base.set",
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

    def _create_secret_group(self, *, name="Workflow secrets"):
        return SecretGroup.objects.create(
            environment=self.environment,
            name=name,
        )

    def _bind_secret(
        self,
        *,
        workflow,
        secret_name,
        variable_name=None,
        provider="environment-variable",
        parameters=None,
        secret_group=None,
    ):
        group = secret_group or workflow.secret_group or self._create_secret_group(name=f"{workflow.name} secrets")
        secret = Secret.objects.create(
            secret_group=group,
            provider=provider,
            name=secret_name,
            parameters=parameters or {"variable": variable_name or secret_name},
        )
        if workflow.secret_group_id != group.pk:
            workflow.secret_group = group
            workflow.save(update_fields=("secret_group",))
        return secret

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
        self.assertContains(response, '"label": "New task"')
        self.assertContains(response, '"label": "Return result"')
        self.assertContains(response, 'data-workflow-run')
        self.assertContains(response, 'data-workflow-execution-status')
        self.assertContains(response, reverse("workflow_designer_run", args=[self.workflow.pk]))
        self.assertContains(response, reverse("workflow_designer_node_run", args=[self.workflow.pk, "__node_id__"]))

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
        self.assertEqual(
            response.context["workflow_connections"],
            [
                {
                    "connection_type": "openai.api",
                    "enabled": True,
                    "id": response.context["workflow_connections"][0]["id"],
                    "integration_id": "openai",
                    "label": "Primary OpenAI (Acme / Operations / production)",
                    "name": "Primary OpenAI",
                    "scope_label": "Acme / Operations / production",
                }
            ],
        )
        catalog_definition = next(
            item
            for item in response.context["workflow_catalog"]["definitions"]
            if item["type"] == "openai.model.chat"
        )
        self.assertEqual(catalog_definition["connection_type"], "openai.api")
        self.assertEqual(catalog_definition["app_label"], "OpenAI")

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
        secret = self._bind_secret(
            workflow=self.workflow,
            secret_name="OPENAI_API_KEY",
        )
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("workflowconnection_add"),
            {
                "environment": self.environment.pk,
                "name": "Primary OpenAI",
                "description": "Main model connection",
                "connection_type": "openai.api",
                "credential_secret": secret.pk,
                "enabled": "on",
                "auth_config": json.dumps({"base_url": "https://api.openai.com/v1"}),
                "metadata": json.dumps({"owner": "automation"}),
            },
        )

        connection = WorkflowConnection.objects.get(name="Primary OpenAI")
        self.assertRedirects(response, connection.get_absolute_url())
        self.assertEqual(connection.environment_id, self.environment.pk)
        self.assertEqual(connection.workspace_id, self.workspace.pk)
        self.assertEqual(connection.organization_id, self.organization.pk)
        self.assertEqual(connection.integration_id, "openai")
        self.assertEqual(connection.credential_secret_id, secret.pk)

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
        self.assertContains(response, "Available connections")
        self.assertContains(response, connection.name)
        self.assertContains(response, reverse("workflowconnection_list"))

    def test_workflow_designer_updates_definition(self):
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
                        "base_url": "https://api.openai.com/v1",
                        "model": "gpt-4.1-mini",
                        "secret_name": "OPENAI_API_KEY",
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
        self.assertEqual(self.workflow.definition["nodes"][0]["type"], "core.manual_trigger")
        self.assertEqual(self.workflow.definition["nodes"][1]["type"], "core.agent")
        self.assertEqual(self.workflow.definition["nodes"][1]["label"], "Planner")
        self.assertEqual(self.workflow.definition["nodes"][2]["type"], "openai.model.chat")
        self.assertEqual(self.workflow.definition["nodes"][3]["type"], "core.response")

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
        self.assertEqual(self.workflow.definition["nodes"][1]["label"], "Reply")
        self.assertEqual(payload["mode"], "workflow")
        self.assertEqual(payload["run"]["status"], "pending")
        run = WorkflowRun.objects.get(pk=payload["run"]["id"])
        execute_workflow_run(run)
        status_response = self.client.get(payload["poll_url"])
        self.assertEqual(status_response.status_code, 200)
        status_payload = status_response.json()
        self.assertEqual(status_payload["run"]["status"], "succeeded")
        self.assertIn("Completed T-42", status_payload["run"]["output_json"])

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
                        "output_key": "tool.output",
                        "value": "Service {{ trigger.payload.service }}",
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
        self._bind_secret(
            workflow=self.workflow,
            secret_name="OPENAI_API_KEY",
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
        self._bind_secret(
            workflow=self.workflow,
            secret_name="OPENAI_API_KEY",
        )
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
        secret = self._bind_secret(
            workflow=workflow,
            secret_name="GITHUB_WEBHOOK_SECRET",
        )
        connection = WorkflowConnection.objects.create(
            environment=self.environment,
            name="Primary GitHub",
            integration_id="github",
            connection_type="github.oauth2",
            credential_secret=secret,
        )
        workflow.definition["nodes"][0]["config"]["connection_id"] = str(connection.pk)
        workflow.save(update_fields=("definition",))
        body = json.dumps({"repository": {"full_name": "acme/platform"}}).encode("utf-8")

        with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": "github-secret"}, clear=False):
            signature = "sha256=" + hmac.new(
                b"github-secret",
                body,
                hashlib.sha256,
            ).hexdigest()
            response = self.client.post(
                reverse("workflow_webhook_trigger", args=[workflow.pk]),
                data=body,
                content_type="application/json",
                HTTP_X_HUB_SIGNATURE_256=signature,
                HTTP_X_GITHUB_EVENT="push",
                HTTP_X_GITHUB_DELIVERY="delivery-1",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "succeeded")
        self.assertEqual(payload["output_data"]["response"], "push:acme/platform")
        run = WorkflowRun.objects.get(pk=payload["run_id"])
        self.assertEqual(run.context_data["trigger"]["meta"]["event"], "push")

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
        secret = self._bind_secret(
            workflow=workflow,
            secret_name="GITHUB_WEBHOOK_SECRET",
        )
        connection = WorkflowConnection.objects.create(
            environment=self.environment,
            name="Primary GitHub",
            integration_id="github",
            connection_type="github.oauth2",
            credential_secret=secret,
        )
        workflow.definition["nodes"][0]["config"]["connection_id"] = str(connection.pk)
        workflow.save(update_fields=("definition",))
        body = json.dumps({"repository": {"full_name": "acme/platform"}}).encode("utf-8")

        with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": "github-secret"}, clear=False):
            signature = "sha256=" + hmac.new(
                b"github-secret",
                body,
                hashlib.sha256,
            ).hexdigest()
            response = self.client.post(
                reverse("workflow_webhook_trigger", args=[workflow.pk]),
                data=body,
                content_type="application/json",
                HTTP_X_HUB_SIGNATURE_256=signature,
                HTTP_X_GITHUB_EVENT="push",
                HTTP_X_GITHUB_DELIVERY="delivery-1",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "succeeded")
        self.assertEqual(payload["output_data"]["response"], "push:acme/platform")
        run = WorkflowRun.objects.get(pk=payload["run_id"])
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
        secret = Secret.objects.create(
            secret_group=self._create_secret_group(name="GitHub auth"),
            provider="environment-variable",
            name="GITHUB_WEBHOOK_SECRET",
            parameters={"variable": "GITHUB_WEBHOOK_SECRET"},
        )
        workflow.secret_group = secret.secret_group
        workflow.save(update_fields=("secret_group",))
        connection = WorkflowConnection.objects.create(
            environment=self.environment,
            name="Primary GitHub",
            integration_id="github",
            connection_type="github.oauth2",
            credential_secret=secret,
        )
        workflow.definition["nodes"][0]["config"]["connection_id"] = str(connection.pk)
        workflow.save(update_fields=("definition",))
        body = json.dumps({"repository": {"full_name": "acme/platform"}}).encode("utf-8")

        with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": "github-secret"}, clear=False):
            signature = "sha256=" + hmac.new(
                b"github-secret",
                body,
                hashlib.sha256,
            ).hexdigest()
            response = self.client.post(
                reverse("workflow_webhook_trigger", args=[workflow.pk]),
                data=body,
                content_type="application/json",
                HTTP_X_HUB_SIGNATURE_256=signature,
                HTTP_X_GITHUB_EVENT="push",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "succeeded")
        self.assertEqual(payload["output_data"]["response"], "push:acme/platform")

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
        secret = self._bind_secret(
            workflow=workflow,
            secret_name="GITHUB_WEBHOOK_SECRET",
        )
        connection = WorkflowConnection.objects.create(
            environment=self.environment,
            name="Primary GitHub",
            integration_id="github",
            connection_type="github.oauth2",
            credential_secret=secret,
        )
        workflow.definition["nodes"][0]["config"]["connection_id"] = str(connection.pk)
        workflow.save(update_fields=("definition",))

        with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": "github-secret"}, clear=False):
            response = self.client.post(
                reverse("workflow_webhook_trigger", args=[workflow.pk]),
                data=json.dumps({"zen": "fail"}),
                content_type="application/json",
                HTTP_X_HUB_SIGNATURE_256="sha256=bad",
                HTTP_X_GITHUB_EVENT="push",
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("signature validation failed", response.json()["detail"].lower())
