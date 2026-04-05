import uuid

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from automation.models import Workflow, WorkflowConnection
from core.models import PrimaryModel
from tenancy.models import Environment, Organization, Workspace


class WorkflowModelTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Acme")
        self.workspace = Workspace.objects.create(
            organization=self.organization,
            name="Operations",
        )
        self.environment = Environment.objects.create(
            workspace=self.workspace,
            name="production",
        )

    def test_workflow_inherits_primary_model(self):
        self.assertTrue(issubclass(Workflow, PrimaryModel))

    def test_workflow_derives_scope_from_environment(self):
        workflow = Workflow(
            environment=self.environment,
            name="Intake triage",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "core.manual_trigger",
                        "label": "New task",
                        "position": {"x": 32, "y": 40},
                    }
                ],
                "edges": [],
            },
        )

        workflow.full_clean()
        workflow.save()

        self.assertEqual(workflow.workspace, self.workspace)
        self.assertEqual(workflow.organization, self.organization)

    def test_workflow_requires_unique_name_per_scope(self):
        Workflow.objects.create(
            environment=self.environment,
            name="Intake triage",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "core.manual_trigger",
                        "label": "New task",
                        "position": {"x": 32, "y": 40},
                    }
                ],
                "edges": [],
            },
        )
        duplicate = Workflow(
            environment=self.environment,
            name="Intake triage",
            definition={
                "nodes": [
                    {
                        "id": "trigger-2",
                        "kind": "trigger",
                        "type": "core.manual_trigger",
                        "label": "Follow-up",
                        "position": {"x": 48, "y": 72},
                    }
                ],
                "edges": [],
            },
        )

        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_workflow_requires_edges_to_reference_existing_nodes(self):
        workflow = Workflow(
            environment=self.environment,
            name="Broken graph",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "core.manual_trigger",
                        "label": "New task",
                        "position": {"x": 32, "y": 40},
                    }
                ],
                "edges": [
                    {
                        "id": "edge-1",
                        "source": "trigger-1",
                        "target": "missing-node",
                    }
                ],
            },
        )

        with self.assertRaises(ValidationError):
            workflow.full_clean()

    def test_workflow_accepts_agent_auxiliary_model_and_tool_edges(self):
        workflow = Workflow(
            environment=self.environment,
            name="Agent attachments",
            definition={
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
                        "label": "AI Agent",
                        "config": {
                            "template": "hello",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {
                            "value_path": "llm.response",
                        },
                        "position": {"x": 608, "y": 40},
                    },
                    {
                        "id": "model-1",
                        "kind": "tool",
                        "type": "openai.model.chat",
                        "label": "OpenAI chat model",
                        "config": {
                            "connection_id": "openai-connection",
                            "model": "gpt-4.1-mini",
                        },
                        "position": {"x": 320, "y": 240},
                    },
                    {
                        "id": "tool-1",
                        "kind": "tool",
                    "type": "core.set",
                    "label": "Set tool",
                    "config": {
                        "mode": "raw",
                        "output_key": "template.result",
                        "json_output": '"Weather summary for {{ trigger.payload.city }}"',
                    },
                        "position": {"x": 480, "y": 240},
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
                    {
                        "id": "edge-4",
                        "source": "tool-1",
                        "sourcePort": "ai_tool",
                        "target": "agent-1",
                        "targetPort": "ai_tool",
                    },
                ],
            },
        )

        workflow.full_clean()

    def test_workflow_allows_empty_definition_as_draft(self):
        workflow = Workflow(
            environment=self.environment,
            name="Draft workflow",
            definition={
                "nodes": [],
                "edges": [],
                "viewport": {"x": 0, "y": 0, "zoom": 1},
            },
        )

        workflow.full_clean()

    def test_workflow_runtime_allows_multiple_trigger_nodes(self):
        workflow = Workflow(
            environment=self.environment,
            name="Multiple triggers",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "core.manual_trigger",
                        "label": "New task",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "trigger-2",
                        "kind": "trigger",
                        "type": "core.manual_trigger",
                        "label": "Retry",
                        "position": {"x": 280, "y": 40},
                    },
                ],
                "edges": [],
            },
        )

        workflow.full_clean()

    def test_workflow_condition_edges_must_use_named_output_ports(self):
        workflow = Workflow(
            environment=self.environment,
            name="Conditional branch",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "core.manual_trigger",
                        "label": "Manual",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "condition-1",
                        "kind": "condition",
                        "type": "core.if",
                        "label": "Check priority",
                        "config": {
                            "conditions": {
                                "conditions": [
                                    {
                                        "leftPath": "trigger.payload.priority",
                                        "operator": "equals",
                                        "rightValue": "high",
                                    }
                                ],
                                "combinator": "and",
                            },
                        },
                        "position": {"x": 280, "y": 40},
                    },
                    {
                        "id": "response-high",
                        "kind": "response",
                        "type": "core.response",
                        "label": "High priority",
                        "position": {"x": 560, "y": 0},
                    },
                    {
                        "id": "response-low",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Low priority",
                        "position": {"x": 560, "y": 120},
                    },
                ],
                "edges": [
                    {
                        "id": "edge-1",
                        "source": "trigger-1",
                        "target": "condition-1",
                    },
                    {
                        "id": "edge-2",
                        "source": "condition-1",
                        "sourcePort": "true",
                        "target": "response-high",
                    },
                ],
            },
        )

        with self.assertRaises(ValidationError):
            workflow.full_clean()

    def test_workflow_accepts_named_tool_catalog_nodes(self):
        workflow = Workflow(
            environment=self.environment,
            name="Catalog tool workflow",
            definition={
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
                    "label": "Render summary",
                    "config": {
                        "mode": "raw",
                        "json_output": '"Org {{ workflow.scope_label }}"',
                        "output_key": "summary",
                    },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {
                            "value_path": "summary",
                        },
                        "position": {"x": 608, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "tool-1"},
                    {"id": "edge-2", "source": "tool-1", "target": "response-1"},
                ],
            },
        )

        workflow.full_clean()

    def test_workflow_accepts_webhook_trigger_and_external_tool_nodes(self):
        workflow = Workflow(
            environment=self.environment,
            name="Webhook and observability workflow",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "github.trigger.webhook",
                        "label": "GitHub webhook",
                        "config": {
                            "owner": "acme",
                            "repository": "ops",
                            "events": "push,pull_request",
                            "connection_id": "github-connection",
                        },
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "tool-1",
                        "kind": "tool",
                        "type": "prometheus.action.query",
                        "label": "Prometheus query",
                        "config": {
                            "query": "up",
                            "output_key": "prometheus.query",
                            "connection_id": "prometheus-connection",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {
                            "value_path": "prometheus.query",
                        },
                        "position": {"x": 608, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "tool-1"},
                    {"id": "edge-2", "source": "tool-1", "target": "response-1"},
                ],
            },
        )

        workflow.full_clean()

    def test_workflow_save_assigns_public_webhook_uuid_path_by_default(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Generated webhook path",
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
                    }
                ],
                "edges": [],
            },
        )

        parameters = workflow.definition["nodes"][0]["parameters"]
        self.assertIn("path", parameters)
        self.assertEqual(str(uuid.UUID(parameters["path"])), parameters["path"])

    def test_workflow_rejects_duplicate_public_webhook_path_across_workflows(self):
        Workflow.objects.create(
            environment=self.environment,
            name="Primary webhook path",
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
                    }
                ],
                "edges": [],
            },
        )

        duplicate = Workflow(
            environment=self.environment,
            name="Duplicate webhook path",
            definition={
                "nodes": [
                    {
                        "id": "trigger-2",
                        "kind": "trigger",
                        "type": "core.webhook_trigger",
                        "label": "Webhook",
                        "config": {
                            "http_method": "POST",
                            "path": "orders/new",
                        },
                        "position": {"x": 48, "y": 72},
                    }
                ],
                "edges": [],
            },
        )

        with self.assertRaises(ValidationError) as context:
            duplicate.save()

        self.assertIn('Webhook path "orders/new" is already used', str(context.exception))

    def test_workflow_rejects_mcp_tool_secret_headers_in_manual_headers_json(self):
        connection = WorkflowConnection(
            environment=self.environment,
            name="Invalid MCP headers workflow",
            integration_id="openai",
            connection_type="openai.api",
        )
        connection.set_data_values(
            {
                "auth_mode": "api_key",
                "base_url": "https://user:hardcoded-secret@api.openai.com/v1",
                "api_key": "sk-test-openai",
            }
        )

        with self.assertRaises(ValidationError) as context:
            connection.full_clean()

        self.assertIn("cannot include embedded credentials in the URL", str(context.exception))
        self.assertIn("Secrets must come from stored workflow connections.", str(context.exception))

    def test_workflow_rejects_external_tool_urls_with_embedded_credentials(self):
        connection = WorkflowConnection(
            environment=self.environment,
            name="Invalid OpenAI URL workflow",
            integration_id="openai",
            connection_type="openai.api",
        )
        connection.set_data_values(
            {
                "auth_mode": "api_key",
                "base_url": "https://user:password@llm.example.com/v1",
                "api_key": "sk-test-openai",
            }
        )

        with self.assertRaises(ValidationError) as context:
            connection.full_clean()

        self.assertIn("cannot include embedded credentials", str(context.exception))
        self.assertIn("Secrets must come from stored workflow connections.", str(context.exception))

    def test_workflow_database_constraint_prevents_duplicates_without_full_clean(self):
        Workflow.objects.create(
            organization=self.organization,
            name="Shared workflow",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "core.manual_trigger",
                        "label": "New task",
                        "position": {"x": 32, "y": 40},
                    }
                ],
                "edges": [],
            },
        )

        with self.assertRaises(IntegrityError):
            Workflow.objects.create(
                organization=self.organization,
                name="Shared workflow",
                definition={
                    "nodes": [
                        {
                            "id": "trigger-2",
                            "kind": "trigger",
                            "type": "core.manual_trigger",
                            "label": "Another trigger",
                            "position": {"x": 48, "y": 72},
                        }
                    ],
                    "edges": [],
                },
            )
