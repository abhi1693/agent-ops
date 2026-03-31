from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from automation.models import Workflow
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
                        "type": "n8n-nodes-base.manualTrigger",
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
                        "type": "n8n-nodes-base.manualTrigger",
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
                        "type": "n8n-nodes-base.manualTrigger",
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
                        "type": "n8n-nodes-base.manualTrigger",
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

    def test_workflow_runtime_requires_exactly_one_trigger_node(self):
        workflow = Workflow(
            environment=self.environment,
            name="Multiple triggers",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "n8n-nodes-base.manualTrigger",
                        "label": "New task",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "trigger-2",
                        "kind": "trigger",
                        "type": "n8n-nodes-base.manualTrigger",
                        "label": "Retry",
                        "position": {"x": 280, "y": 40},
                    },
                ],
                "edges": [],
            },
        )

        with self.assertRaises(ValidationError):
            workflow.full_clean()

    def test_workflow_condition_targets_must_match_connected_edges(self):
        workflow = Workflow(
            environment=self.environment,
            name="Conditional branch",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "n8n-nodes-base.manualTrigger",
                        "label": "Manual",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "condition-1",
                        "kind": "condition",
                        "type": "n8n-nodes-base.if",
                        "label": "Check priority",
                        "config": {
                            "path": "trigger.payload.priority",
                            "operator": "equals",
                            "right_value": "high",
                            "true_target": "response-high",
                            "false_target": "response-low",
                        },
                        "position": {"x": 280, "y": 40},
                    },
                    {
                        "id": "response-high",
                        "kind": "response",
                        "type": "response",
                        "label": "High priority",
                        "position": {"x": 560, "y": 0},
                    },
                    {
                        "id": "response-low",
                        "kind": "response",
                        "type": "response",
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
                        "type": "n8n-nodes-base.manualTrigger",
                        "label": "Manual",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "tool-1",
                        "kind": "tool",
                        "type": "tool.template",
                        "label": "Render summary",
                        "config": {
                            "template": "Org {{ workflow.scope_label }}",
                            "output_key": "summary",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "response",
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

    def test_workflow_rejects_legacy_tool_name_selector_on_typed_app_node(self):
        workflow = Workflow(
            environment=self.environment,
            name="Mismatched concrete tool workflow",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "n8n-nodes-base.manualTrigger",
                        "label": "Manual",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "tool-1",
                        "kind": "tool",
                        "type": "tool.template",
                        "label": "Render summary",
                        "config": {
                            "tool_name": "secret",
                            "template": "Org {{ workflow.scope_label }}",
                            "output_key": "summary",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "response",
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

        with self.assertRaises(ValidationError) as context:
            workflow.full_clean()

        self.assertIn("legacy selector fields: config.tool_name", str(context.exception))

    def test_workflow_accepts_webhook_trigger_and_external_tool_nodes(self):
        workflow = Workflow(
            environment=self.environment,
            name="Webhook and observability workflow",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "trigger.github",
                        "label": "GitHub webhook",
                        "config": {
                            "signature_secret_name": "GITHUB_WEBHOOK_SECRET",
                            "events": "push,pull_request",
                        },
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "tool-1",
                        "kind": "tool",
                        "type": "tool.prometheus_query",
                        "label": "Prometheus query",
                        "config": {
                            "base_url": "https://prometheus.example.com",
                            "query": "up",
                            "output_key": "prometheus.query",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "response",
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

    def test_workflow_rejects_mcp_tool_secret_headers_in_manual_headers_json(self):
        workflow = Workflow(
            environment=self.environment,
            name="Invalid MCP headers workflow",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "n8n-nodes-base.manualTrigger",
                        "label": "Manual",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "tool-1",
                        "kind": "tool",
                        "type": "tool.mcp_server",
                        "label": "MCP server",
                        "config": {
                            "server_url": "https://mcp.example.com/mcp",
                            "remote_tool_name": "weather_current",
                            "headers_json": {
                                "Authorization": "Bearer hardcoded-secret",
                            },
                            "output_key": "mcp.result",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "response",
                        "label": "Done",
                        "config": {
                            "value_path": "mcp.result",
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

        with self.assertRaises(ValidationError) as context:
            workflow.full_clean()

        self.assertIn("Secrets must come from stored Secret objects", str(context.exception))

    def test_workflow_rejects_external_tool_urls_with_embedded_credentials(self):
        workflow = Workflow(
            environment=self.environment,
            name="Invalid OpenAI URL workflow",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "n8n-nodes-base.manualTrigger",
                        "label": "Manual",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "agent-1",
                        "kind": "agent",
                        "type": "agent",
                        "label": "LLM chat",
                        "config": {
                            "base_url": "https://user:password@llm.example.com/v1",
                            "api_key_name": "OPENAI_API_KEY",
                            "model": "gpt-4.1-mini",
                            "template": "hello",
                            "output_key": "llm.response",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "response",
                        "label": "Done",
                        "config": {
                            "value_path": "llm.response",
                        },
                        "position": {"x": 608, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "agent-1"},
                    {"id": "edge-2", "source": "agent-1", "target": "response-1"},
                ],
            },
        )

        with self.assertRaises(ValidationError) as context:
            workflow.full_clean()

        self.assertIn("cannot include embedded credentials", str(context.exception))

    def test_workflow_database_constraint_prevents_duplicates_without_full_clean(self):
        Workflow.objects.create(
            organization=self.organization,
            name="Shared workflow",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "n8n-nodes-base.manualTrigger",
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
                            "type": "n8n-nodes-base.manualTrigger",
                            "label": "Another trigger",
                            "position": {"x": 48, "y": 72},
                        }
                    ],
                    "edges": [],
                },
            )
