import os
import subprocess
import tempfile
from copy import deepcopy
from json import loads
from unittest.mock import patch
from urllib.parse import parse_qs

from django.test import TestCase, TransactionTestCase

from automation.models import Workflow, WorkflowConnection, WorkflowConnectionState, WorkflowRun, WorkflowStepRun, WorkflowVersion
from automation.runtime import (
    _initialize_workflow_run,
    execute_workflow,
    execute_workflow_node_preview,
    execute_workflow_run,
)
from tenancy.models import Environment, Organization, Workspace


class _FakeJsonResponse:
    def __init__(self, payload, *, status=200, content_type="application/json", headers=None, raw_body=None):
        self._payload = payload
        self._status = status
        self._raw_body = raw_body
        self.headers = {"Content-Type": content_type, **(headers or {})}

    def read(self):
        import json

        if self._raw_body is not None:
            return self._raw_body
        return json.dumps(self._payload).encode("utf-8")

    def getcode(self):
        return self._status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class WorkflowRuntimeTests(TestCase):
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
        node = self._node(workflow, node_id)
        config = dict(node.get("config") or {})
        config.pop("connection_id", None)
        config.pop("base_url", None)
        config.pop("secret_name", None)
        config.pop("secret_group_id", None)
        config["connection_id"] = str(connection.pk)
        node["config"] = config
        workflow.save(update_fields=("definition",))
        return connection

    def _node(self, workflow, node_id):
        for node in workflow.definition.get("nodes", []):
            if node.get("id") == node_id:
                return node
        raise AssertionError(f"Workflow {workflow.pk} does not define node {node_id}.")

    def _create_incident_triage_workflow(self):
        return Workflow.objects.create(
            environment=self.environment,
            name="Incident triage example",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "core.manual_trigger",
                        "label": "Manual trigger",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "set-ticket-context",
                        "kind": "tool",
                        "type": "core.set",
                        "label": "Capture incident",
                        "config": {
                            "mode": "raw",
                            "output_key": "incident.summary",
                            "json_output": {
                                "ticket_id": "{{ trigger.payload.ticket_id }}",
                                "service": "{{ trigger.payload.service }}",
                                "severity": "{{ trigger.payload.severity }}",
                                "environment": "{{ trigger.payload.environment }}",
                            },
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "if-production",
                        "kind": "control",
                        "type": "core.if",
                        "label": "Production only",
                        "config": {
                            "combinator": "and",
                            "conditions": {
                                "conditions": [
                                    {
                                        "leftPath": "runtime.inputs_by_alias.set_ticket_context.output.value.environment",
                                        "operator": "equals",
                                        "rightValue": "production",
                                    }
                                ],
                            },
                        },
                        "position": {"x": 608, "y": 40},
                    },
                    {
                        "id": "stop-non-production",
                        "kind": "control",
                        "type": "core.stop_and_error",
                        "label": "Reject non-production",
                        "config": {
                            "message": "Environment {{ incident.summary.environment }} is not eligible for paging.",
                        },
                        "position": {"x": 896, "y": 160},
                    },
                    {
                        "id": "switch-severity",
                        "kind": "control",
                        "type": "core.switch",
                        "label": "Choose escalation path",
                        "config": {
                            "mode": "rules",
                            "rules": {
                                "values": [
                                    {
                                        "leftPath": "incident.summary.severity",
                                        "operator": "equals",
                                        "rightValue": "critical",
                                    },
                                    {
                                        "leftPath": "incident.summary.severity",
                                        "operator": "equals",
                                        "rightValue": "high",
                                    },
                                ]
                            },
                        },
                        "position": {"x": 896, "y": 40},
                    },
                    {
                        "id": "set-route-p1",
                        "kind": "tool",
                        "type": "core.set",
                        "label": "Route P1",
                        "config": {
                            "mode": "raw",
                            "output_key": "incident.route",
                            "json_output": {
                                "team": "platform-oncall",
                                "priority": "p1",
                                "channel": "pagerduty",
                                "summary": "{{ incident.summary.ticket_id }} {{ incident.summary.service }} critical in {{ incident.summary.environment }}",
                            },
                        },
                        "position": {"x": 1184, "y": -80},
                    },
                    {
                        "id": "set-route-p2",
                        "kind": "tool",
                        "type": "core.set",
                        "label": "Route P2",
                        "config": {
                            "mode": "raw",
                            "output_key": "incident.route",
                            "json_output": {
                                "team": "service-owners",
                                "priority": "p2",
                                "channel": "slack",
                                "summary": "{{ incident.summary.ticket_id }} {{ incident.summary.service }} high severity in {{ incident.summary.environment }}",
                            },
                        },
                        "position": {"x": 1184, "y": 40},
                    },
                    {
                        "id": "set-route-general",
                        "kind": "tool",
                        "type": "core.set",
                        "label": "Route General",
                        "config": {
                            "mode": "raw",
                            "output_key": "incident.route",
                            "json_output": {
                                "team": "support-triage",
                                "priority": "p3",
                                "channel": "queue",
                                "summary": "{{ incident.summary.ticket_id }} {{ incident.summary.service }} needs triage in {{ incident.summary.environment }}",
                            },
                        },
                        "position": {"x": 1184, "y": 160},
                    },
                    {
                        "id": "response-dispatch",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Dispatch result",
                        "config": {
                            "value_path": "runtime.inputs.0.output.value",
                        },
                        "position": {"x": 1472, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "set-ticket-context"},
                    {"id": "edge-2", "source": "set-ticket-context", "target": "if-production"},
                    {"id": "edge-3", "source": "if-production", "sourcePort": "true", "target": "switch-severity"},
                    {
                        "id": "edge-4",
                        "source": "if-production",
                        "sourcePort": "false",
                        "target": "stop-non-production",
                    },
                    {"id": "edge-5", "source": "switch-severity", "sourcePort": "case_1", "target": "set-route-p1"},
                    {"id": "edge-6", "source": "switch-severity", "sourcePort": "case_2", "target": "set-route-p2"},
                    {
                        "id": "edge-7",
                        "source": "switch-severity",
                        "sourcePort": "fallback",
                        "target": "set-route-general",
                    },
                    {"id": "edge-8", "source": "set-route-p1", "target": "response-dispatch"},
                    {"id": "edge-9", "source": "set-route-p2", "target": "response-dispatch"},
                    {"id": "edge-10", "source": "set-route-general", "target": "response-dispatch"},
                ],
            },
        )

    def test_execute_workflow_runs_agent_llm_step_end_to_end(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Built-in runtime",
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
            },
        )
        self._attach_openai_connection(workflow)

        def fake_urlopen(request, timeout=20):
            self.assertEqual(timeout, 20)
            self.assertEqual(request.full_url, "https://api.openai.com/v1/chat/completions")
            self.assertEqual(request.headers["Authorization"], "Bearer sk-test-openai")
            body = loads(request.data.decode("utf-8"))
            self.assertEqual(body["model"], "gpt-4.1-mini")
            self.assertEqual(body["messages"][0]["role"], "user")
            self.assertEqual(body["messages"][0]["content"], "Review T-42")
            return _FakeJsonResponse(
                {
                    "id": "chatcmpl-001",
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

        with patch("automation.tools.base.urlopen", side_effect=fake_urlopen):
            run = execute_workflow(
                workflow,
                input_data={"ticket_id": "T-42"},
            )

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.output_data["response"], "Completed Review T-42")
        self.assertEqual(run.context_data["llm"]["response"]["text"], "Review T-42")
        self.assertEqual(run.step_count, 3)

    def test_execute_workflow_runs_incident_triage_example_end_to_end(self):
        workflow = self._create_incident_triage_workflow()

        run = execute_workflow(
            workflow,
            input_data={
                "ticket_id": "INC-100",
                "service": "payments",
                "severity": "critical",
                "environment": "production",
            },
        )

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.output_data["response"]["team"], "platform-oncall")
        self.assertEqual(run.output_data["response"]["priority"], "p1")
        self.assertEqual(run.context_data["incident"]["summary"]["ticket_id"], "INC-100")
        self.assertEqual(run.context_data["incident"]["route"]["channel"], "pagerduty")
        self.assertCountEqual(
            run.scheduler_state["completed_node_ids"],
            [
                "trigger-1",
                "set-ticket-context",
                "if-production",
                "switch-severity",
                "set-route-p1",
                "response-dispatch",
            ],
        )
        self.assertEqual(
            run.scheduler_state["skipped_predecessors"]["set-route-p2"],
            ["switch-severity"],
        )
        self.assertEqual(
            run.scheduler_state["skipped_predecessors"]["set-route-general"],
            ["switch-severity"],
        )

    def test_execute_workflow_can_stop_after_each_incident_triage_node_id(self):
        workflow = self._create_incident_triage_workflow()
        input_data = {
            "ticket_id": "INC-101",
            "service": "billing",
            "severity": "critical",
            "environment": "production",
        }
        expected_by_node_id = {
            "trigger-1": lambda run: self.assertEqual(
                run.output_data["output"]["payload"]["ticket_id"],
                "INC-101",
            ),
            "set-ticket-context": lambda run: self.assertEqual(
                run.output_data["output"]["value"]["service"],
                "billing",
            ),
            "if-production": lambda run: self.assertTrue(run.output_data["output"]["matched"]),
            "switch-severity": lambda run: self.assertEqual(
                run.output_data["output"]["matched_case"],
                "case_1",
            ),
            "set-route-p1": lambda run: self.assertEqual(
                run.output_data["output"]["value"]["team"],
                "platform-oncall",
            ),
            "response-dispatch": lambda run: self.assertEqual(
                run.output_data["response"]["response"]["team"],
                "platform-oncall",
            ),
        }

        for node_id, assertion in expected_by_node_id.items():
            with self.subTest(node_id=node_id):
                run = execute_workflow(
                    workflow,
                    input_data=input_data,
                    trigger_mode="manual:node",
                    stop_after_node_id=node_id,
                )
                self.assertEqual(run.status, "succeeded")
                self.assertEqual(run.output_data["node_id"], node_id)
                assertion(run)

    def test_execute_workflow_runs_incident_triage_non_production_failure_path(self):
        workflow = self._create_incident_triage_workflow()

        run = execute_workflow(
            workflow,
            input_data={
                "ticket_id": "INC-102",
                "service": "payments",
                "severity": "critical",
                "environment": "staging",
            },
        )

        self.assertEqual(run.status, "failed")
        self.assertEqual(
            run.output_data["message"],
            "Environment staging is not eligible for paging.",
        )
        self.assertCountEqual(
            run.scheduler_state["completed_node_ids"],
            ["trigger-1", "set-ticket-context", "if-production", "stop-non-production"],
        )

    def test_execute_workflow_respects_static_mode_for_agent_prompt_template(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Static agent prompt",
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
                        "label": "Draft",
                        "config": {
                            "template": "Review {{ trigger.payload.ticket_id }}",
                            "__input_modes": {
                                "template": "static",
                            },
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
                            "value_path": "llm.response.text",
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
            },
        )
        self._attach_openai_connection(workflow)

        def fake_urlopen(request, timeout=20):
            self.assertEqual(timeout, 20)
            body = loads(request.data.decode("utf-8"))
            self.assertEqual(body["messages"][0]["content"], "Review {{ trigger.payload.ticket_id }}")
            return _FakeJsonResponse(
                {
                    "id": "chatcmpl-002",
                    "model": "gpt-4.1-mini",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "content": "Static prompt preserved",
                            },
                        }
                    ],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16},
                }
            )

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai"}, clear=False):
            with patch("automation.tools.base.urlopen", side_effect=fake_urlopen):
                run = execute_workflow(
                    workflow,
                    input_data={"ticket_id": "T-42"},
                )

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.output_data["response"], "Static prompt preserved")

    def test_execute_workflow_supports_fanout_and_join(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Fanout join",
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
                        "label": "Branch root",
                        "config": {
                            "mode": "raw",
                            "output_key": "branch.root",
                            "json_output": '"fanout {{ trigger.payload.ticket_id }}"',
                        },
                        "position": {"x": 320, "y": 60},
                    },
                    {
                        "id": "set-1",
                        "kind": "tool",
                        "type": "core.set",
                        "label": "Branch one",
                        "config": {
                            "mode": "raw",
                            "output_key": "branch.one",
                            "json_output": '"alpha"',
                        },
                        "position": {"x": 608, "y": 0},
                    },
                    {
                        "id": "set-2",
                        "kind": "tool",
                        "type": "core.set",
                        "label": "Branch two",
                        "config": {
                            "mode": "raw",
                            "output_key": "branch.two",
                            "json_output": '"beta"',
                        },
                        "position": {"x": 608, "y": 120},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {
                            "template": "{{ branch.one }}|{{ branch.two }}",
                        },
                        "position": {"x": 608, "y": 60},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "tool-1"},
                    {"id": "edge-2", "source": "tool-1", "target": "set-1"},
                    {"id": "edge-3", "source": "tool-1", "target": "set-2"},
                    {"id": "edge-4", "source": "set-1", "target": "response-1"},
                    {"id": "edge-5", "source": "set-2", "target": "response-1"},
                ],
            },
        )

        run = execute_workflow(workflow, input_data={"ticket_id": "T-77"})

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.output_data["response"], "alpha|beta")
        self.assertEqual(run.context_data["branch"]["one"], "alpha")
        self.assertEqual(run.context_data["branch"]["two"], "beta")
        self.assertEqual(run.step_count, 5)
        self.assertEqual(run.context_data["__runtime"]["node_outputs"]["set-1"]["output"]["value"], "alpha")
        self.assertEqual(run.context_data["__runtime"]["node_outputs"]["set-2"]["output"]["value"], "beta")
        self.assertCountEqual(
            run.scheduler_state["completed_node_ids"],
            ["trigger-1", "tool-1", "set-1", "set-2", "response-1"],
        )
        response_step = WorkflowStepRun.objects.get(run=run, node_id="response-1")
        self.assertCountEqual(
            [item["source_node_id"] for item in response_step.input_data["input_items"]],
            ["set-1", "set-2"],
        )
        self.assertCountEqual(
            [item["output"]["value"] for item in response_step.input_data["input_items"]],
            ["alpha", "beta"],
        )

    def test_execute_workflow_existing_nodes_can_read_runtime_input_aliases(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Existing nodes runtime aliases",
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
                        "id": "if-1",
                        "kind": "control",
                        "type": "core.if",
                        "label": "Check status",
                        "config": {
                            "combinator": "and",
                            "conditions": {
                                "conditions": [
                                    {
                                        "leftPath": "runtime.inputs_by_alias.trigger_1.output.payload.status",
                                        "operator": "equals",
                                        "rightValue": "queued",
                                    }
                                ],
                            },
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "set-1",
                        "kind": "tool",
                        "type": "core.set",
                        "label": "Record branch",
                        "config": {
                            "mode": "raw",
                            "output_key": "derived.branch",
                            "json_output": '"{{ runtime.inputs_by_alias.if_1.output.next_port }}"',
                        },
                        "position": {"x": 608, "y": 0},
                    },
                    {
                        "id": "response-true",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {
                            "value_path": "runtime.inputs_by_alias.set_1.output.value",
                        },
                        "position": {"x": 896, "y": 0},
                    },
                    {
                        "id": "response-false",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Skipped",
                        "config": {
                            "template": "not-queued",
                        },
                        "position": {"x": 608, "y": 120},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "if-1"},
                    {"id": "edge-2", "source": "if-1", "sourcePort": "true", "target": "set-1"},
                    {"id": "edge-3", "source": "if-1", "sourcePort": "false", "target": "response-false"},
                    {"id": "edge-4", "source": "set-1", "target": "response-true"},
                ],
            },
        )

        run = execute_workflow(workflow, input_data={"status": "queued"})

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.output_data["response"], "true")
        self.assertEqual(run.context_data["derived"]["branch"], "true")
        self.assertCountEqual(
            run.scheduler_state["completed_node_ids"],
            ["trigger-1", "if-1", "set-1", "response-true"],
        )
        self.assertEqual(
            run.context_data["__runtime"]["node_outputs"]["if-1"]["output"]["next_port"],
            "true",
        )
        self.assertEqual(run.scheduler_state["skipped_node_ids"], [])
        self.assertEqual(run.scheduler_state["skipped_predecessors"]["response-false"], ["if-1"])
        self.assertEqual(
            WorkflowStepRun.objects.get(run=run, node_id="if-1").output_data["next_port"],
            "true",
        )

    def test_execute_workflow_allows_expression_mode_for_literal_input_fields(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Expression set value",
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
                        "id": "set-1",
                        "kind": "tool",
                        "type": "core.set",
                        "label": "Set draft",
                        "config": {
                            "mode": "raw",
                            "output_key": "draft",
                            "json_output": '"{{ trigger.payload.ticket_id }}"',
                            "__input_modes": {
                                "json_output": "expression",
                            },
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {
                            "value_path": "draft",
                        },
                        "position": {"x": 608, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "set-1"},
                    {"id": "edge-2", "source": "set-1", "target": "response-1"},
                ],
            },
        )

        run = execute_workflow(workflow, input_data={"ticket_id": "T-42"})

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.context_data["draft"], "T-42")
        self.assertEqual(run.output_data["response"], "T-42")

    def test_execute_workflow_allows_expression_mode_for_input_path_fields(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Expression response value path",
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
                        "id": "set-1",
                        "kind": "tool",
                        "type": "core.set",
                        "label": "Set draft",
                        "config": {
                            "mode": "raw",
                            "output_key": "draft.result",
                            "json_output": '"resolved"',
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {
                            "value_path": "{{ trigger.payload.destination }}",
                            "__input_modes": {
                                "value_path": "expression",
                            },
                        },
                        "position": {"x": 608, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "set-1"},
                    {"id": "edge-2", "source": "set-1", "target": "response-1"},
                ],
            },
        )

        run = execute_workflow(workflow, input_data={"destination": "draft.result"})

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.context_data["draft"]["result"], "resolved")
        self.assertEqual(run.output_data["response"], "resolved")

    def test_execute_workflow_persists_workflow_version_and_step_runs(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Durable runtime state",
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
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {
                            "template": "Completed {{ trigger.payload.ticket_id }}",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
                ],
            },
        )

        run = execute_workflow(workflow, input_data={"ticket_id": "T-42"})

        self.assertIsNotNone(run.workflow_version_id)
        self.assertEqual(WorkflowVersion.objects.count(), 1)
        self.assertEqual(run.workflow_version.workflow_id, workflow.id)
        self.assertEqual(run.workflow_version.version, 1)
        self.assertEqual(run.workflow_version.definition["definition_version"], 2)
        self.assertEqual(run.workflow_version.definition["nodes"][1]["name"], "Done")

        step_runs = list(run.step_runs.order_by("sequence"))
        self.assertEqual(WorkflowStepRun.objects.count(), 2)
        self.assertEqual([step.node_id for step in step_runs], ["trigger-1", "response-1"])
        self.assertEqual([step.status for step in step_runs], ["succeeded", "succeeded"])
        self.assertEqual(step_runs[0].output_data["payload"], {"ticket_id": "T-42"})
        self.assertEqual(step_runs[1].output_data["response"], "Completed T-42")
        self.assertEqual(step_runs[0].workflow_version_id, run.workflow_version_id)
        self.assertEqual(step_runs[1].workflow_version_id, run.workflow_version_id)

    def test_execute_workflow_reuses_existing_version_until_definition_changes(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Versioned runtime",
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
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {
                            "template": "v1",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
                ],
            },
        )

        first_run = execute_workflow(workflow)
        second_run = execute_workflow(workflow)

        self.assertEqual(first_run.workflow_version_id, second_run.workflow_version_id)
        self.assertEqual(WorkflowVersion.objects.count(), 1)

        updated_definition = deepcopy(workflow.definition)
        for node in updated_definition.get("nodes", []):
            if node.get("id") == "response-1":
                node.setdefault("parameters", {})["template"] = "v2"
                break
        else:
            self.fail(f"Workflow {workflow.pk} does not define node response-1.")
        workflow.definition = updated_definition
        workflow.save(update_fields=("definition",))

        third_run = execute_workflow(workflow)

        self.assertNotEqual(third_run.workflow_version_id, first_run.workflow_version_id)
        self.assertEqual(
            list(
                WorkflowVersion.objects.filter(workflow=workflow)
                .order_by("version")
                .values_list("version", flat=True)
            ),
            [1, 2],
        )

    def test_execute_workflow_can_stop_after_selected_node(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Stop at node",
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
                        "label": "Render",
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
            },
        )

        run = execute_workflow(
            workflow,
            input_data={"service": "payments"},
            trigger_mode="manual:node",
            stop_after_node_id="tool-1",
        )

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.step_count, 2)
        self.assertEqual(run.output_data["node_id"], "tool-1")
        self.assertEqual(run.output_data["output"]["value"], "Service payments")
        self.assertEqual(run.context_data["tool"]["output"], "Service payments")

    def test_execute_workflow_node_preview_executes_auxiliary_model_node_in_isolation(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Preview auxiliary node",
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
            },
        )
        self._attach_openai_connection(workflow)

        run = execute_workflow_node_preview(
            workflow,
            node_id="model-1",
            input_data={"ticket_id": "T-42"},
        )

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.trigger_mode, "manual:node")
        self.assertEqual(run.step_count, 1)
        self.assertEqual(run.output_data["node_id"], "model-1")
        self.assertEqual(run.output_data["output"]["model"], "gpt-4.1-mini")

    def test_execute_workflow_node_preview_rejects_disabled_node(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Preview disabled node",
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
                        "label": "Disabled set",
                        "disabled": True,
                        "config": {
                            "mode": "raw",
                            "output_key": "tool.output",
                            "json_output": '"hello"',
                        },
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "tool-1"},
                ],
            },
        )

        run = execute_workflow_node_preview(
            workflow,
            node_id="tool-1",
            input_data={"ticket_id": "T-42"},
        )

        self.assertEqual(run.status, "failed")
        self.assertIn('Node "tool-1" is disabled and cannot be previewed.', run.error)
        self.assertEqual(run.step_count, 0)

    def test_execute_workflow_skips_disabled_nodes(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Skip disabled node",
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
                        "label": "Disabled set",
                        "disabled": True,
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
                            "template": "Completed {{ trigger.payload.service }}",
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

        run = execute_workflow(
            workflow,
            input_data={"service": "payments"},
        )

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.output_data["response"], "Completed payments")
        self.assertEqual(run.step_count, 2)
        self.assertEqual(run.scheduler_state["skipped_node_ids"], ["tool-1"])
        self.assertEqual([step["node_id"] for step in run.step_results], ["trigger-1", "response-1"])

    def test_execute_workflow_runs_core_catalog_nodes_end_to_end(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="core catalog nodes",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "core.manual_trigger",
                        "label": "Manual Trigger",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "set-1",
                        "kind": "tool",
                        "type": "core.set",
                        "label": "Set",
                        "config": {
                            "mode": "raw",
                            "output_key": "context.value",
                            "json_output": '"hello"',
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "if-1",
                        "kind": "condition",
                        "type": "core.if",
                        "label": "If",
                        "config": {
                            "combinator": "and",
                            "conditions": {
                                "conditions": [
                                    {
                                        "leftPath": "context.value",
                                        "operator": "equals",
                                        "rightValue": "hello",
                                    }
                                ],
                            },
                        },
                        "position": {"x": 608, "y": 40},
                    },
                    {
                        "id": "response-hello",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Matched",
                        "config": {
                            "value_path": "context.value",
                        },
                        "position": {"x": 896, "y": 0},
                    },
                    {
                        "id": "response-other",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Fallback",
                        "config": {
                            "template": "miss",
                        },
                        "position": {"x": 896, "y": 120},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "set-1"},
                    {"id": "edge-2", "source": "set-1", "target": "if-1"},
                    {"id": "edge-3", "source": "if-1", "sourcePort": "true", "target": "response-hello"},
                    {"id": "edge-4", "source": "if-1", "sourcePort": "false", "target": "response-other"},
                ],
            },
        )

        run = execute_workflow(workflow)

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.output_data["response"], "hello")
        self.assertEqual(run.context_data["context"]["value"], "hello")
        self.assertEqual(run.step_count, 4)

    def test_execute_workflow_runs_v2_catalog_builtins_end_to_end(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="v2 built-ins",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "core.manual_trigger",
                        "label": "Manual Trigger",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "set-1",
                        "kind": "tool",
                        "type": "core.set",
                        "label": "Set",
                        "config": {
                            "mode": "raw",
                            "output_key": "context.value",
                            "json_output": '"hello"',
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "if-1",
                        "kind": "condition",
                        "type": "core.if",
                        "label": "If",
                        "config": {
                            "combinator": "and",
                            "conditions": {
                                "conditions": [
                                    {
                                        "leftPath": "context.value",
                                        "operator": "equals",
                                        "rightValue": "hello",
                                    }
                                ],
                            },
                        },
                        "position": {"x": 608, "y": 40},
                    },
                    {
                        "id": "response-hello",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Matched",
                        "config": {
                            "value_path": "context.value",
                        },
                        "position": {"x": 896, "y": 0},
                    },
                    {
                        "id": "response-other",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Fallback",
                        "config": {
                            "template": "miss",
                        },
                        "position": {"x": 896, "y": 120},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "set-1"},
                    {"id": "edge-2", "source": "set-1", "target": "if-1"},
                    {"id": "edge-3", "source": "if-1", "sourcePort": "true", "target": "response-hello"},
                    {"id": "edge-4", "source": "if-1", "sourcePort": "false", "target": "response-other"},
                ],
            },
        )

        run = execute_workflow(workflow)

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.output_data["response"], "hello")
        self.assertEqual(run.context_data["context"]["value"], "hello")
        self.assertEqual(run.step_count, 4)

    def test_execute_workflow_runs_v2_catalog_agent_with_openai_connection(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="v2 agent runtime",
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
                        "label": "Draft",
                        "config": {
                            "template": "Review {{ trigger.payload.ticket_id }}",
                            "output_key": "llm.response",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "model-1",
                        "kind": "tool",
                        "type": "openai.model.chat",
                        "label": "OpenAI chat model",
                        "config": {
                            "connection_id": "",
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
            },
        )
        connection = self._create_connection(
            environment=self.environment,
            name="Primary OpenAI",
            integration_id="openai",
            connection_type="openai.api",
            data={
                "auth_mode": "api_key",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-test-openai",
            },
        )
        self._node(workflow, "model-1")["connections"] = {"connection_id": str(connection.pk)}
        workflow.save(update_fields=("definition",))

        def fake_urlopen(request, timeout=20):
            self.assertEqual(timeout, 20)
            self.assertEqual(request.full_url, "https://api.openai.com/v1/chat/completions")
            self.assertEqual(request.headers["Authorization"], "Bearer sk-test-openai")
            body = loads(request.data.decode("utf-8"))
            self.assertEqual(body["model"], "gpt-4.1-mini")
            self.assertEqual(body["messages"][0]["role"], "user")
            self.assertEqual(body["messages"][0]["content"], "Review T-42")
            return _FakeJsonResponse(
                {
                    "id": "chatcmpl-101",
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

        with patch("automation.tools.base.urlopen", side_effect=fake_urlopen):
            run = execute_workflow(
                workflow,
                input_data={"ticket_id": "T-42"},
            )

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.output_data["response"], "Completed Review T-42")
        self.assertEqual(run.context_data["llm"]["response"]["text"], "Review T-42")
        self.assertEqual(run.step_count, 3)

    def test_execute_workflow_runs_v2_catalog_agent_with_typed_openai_connection(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="v2 agent runtime typed connection",
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
                        "label": "Draft",
                        "config": {
                            "template": "Review {{ trigger.payload.ticket_id }}",
                            "output_key": "llm.response",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "model-1",
                        "kind": "tool",
                        "type": "openai.model.chat",
                        "label": "OpenAI chat model",
                        "config": {
                            "connection_id": "",
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
            },
        )
        connection = self._create_connection(
            environment=self.environment,
            name="Typed OpenAI",
            integration_id="openai",
            connection_type="openai.api",
            data={
                "auth_mode": "api_key",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-test-openai",
            },
        )
        self._node(workflow, "model-1")["connections"] = {"connection_id": str(connection.pk)}
        workflow.save(update_fields=("definition",))

        def fake_urlopen(request, timeout=20):
            self.assertEqual(timeout, 20)
            self.assertEqual(request.full_url, "https://api.openai.com/v1/chat/completions")
            self.assertEqual(request.headers["Authorization"], "Bearer sk-test-openai")
            body = loads(request.data.decode("utf-8"))
            self.assertEqual(body["model"], "gpt-4.1-mini")
            self.assertEqual(body["messages"][0]["content"], "Review T-99")
            return _FakeJsonResponse(
                {
                    "id": "chatcmpl-typed-101",
                    "model": "gpt-4.1-mini",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "content": "Review T-99",
                            },
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
                }
            )

        with patch("automation.tools.base.urlopen", side_effect=fake_urlopen):
            run = execute_workflow(
                workflow,
                input_data={"ticket_id": "T-99"},
            )

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.output_data["response"], "Completed Review T-99")
        self.assertEqual(run.context_data["llm"]["response"]["text"], "Review T-99")

    def test_execute_workflow_uses_openai_oauth_access_token_state(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="v2 agent runtime oauth connection",
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
                        "label": "Draft",
                        "config": {
                            "template": "Review {{ trigger.payload.ticket_id }}",
                            "output_key": "llm.response",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "model-1",
                        "kind": "tool",
                        "type": "openai.model.chat",
                        "label": "OpenAI chat model",
                        "config": {
                            "connection_id": "",
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
            },
        )
        connection = self._create_connection(
            environment=self.environment,
            name="OpenAI OAuth",
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
                "access_token": "oauth-access-live",
                "refresh_token": "oauth-refresh-live",
                "expires_at": 4102444800,
                "account_id": "acct_live",
            },
        )
        self._node(workflow, "model-1")["connections"] = {"connection_id": str(connection.pk)}
        workflow.save(update_fields=("definition",))

        def fake_urlopen(request, timeout=20):
            self.assertEqual(timeout, 20)
            self.assertEqual(request.full_url, "https://api.openai.com/v1/chat/completions")
            self.assertEqual(request.headers["Authorization"], "Bearer oauth-access-live")
            body = loads(request.data.decode("utf-8"))
            self.assertEqual(body["messages"][0]["content"], "Review T-77")
            return _FakeJsonResponse(
                {
                    "id": "chatcmpl-oauth-1",
                    "model": "gpt-4.1-mini",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": "Review T-77"},
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
                }
            )

        with patch("automation.tools.base.urlopen", side_effect=fake_urlopen):
            run = execute_workflow(workflow, input_data={"ticket_id": "T-77"})

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.output_data["response"], "Completed Review T-77")

    def test_execute_workflow_refreshes_openai_oauth_access_token_state(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="v2 agent runtime oauth refresh",
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
                        "label": "Draft",
                        "config": {
                            "template": "Review {{ trigger.payload.ticket_id }}",
                            "output_key": "llm.response",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "model-1",
                        "kind": "tool",
                        "type": "openai.model.chat",
                        "label": "OpenAI chat model",
                        "config": {
                            "connection_id": "",
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
            },
        )
        connection = self._create_connection(
            environment=self.environment,
            name="OpenAI OAuth Refresh",
            integration_id="openai",
            connection_type="openai.api",
            data={
                "auth_mode": "oauth2_authorization_code",
                "base_url": "https://api.openai.com/v1",
                "oauth_client_id": "client-openai-123",
                "oauth_token_url": "https://auth.openai.com/oauth/token",
                "oauth_client_secret": "sk-test-client-secret",
            },
        )
        state = WorkflowConnectionState.objects.create(
            connection=connection,
            state_values={
                "access_token": "oauth-access-expired",
                "refresh_token": "oauth-refresh-old",
                "expires_at": 1,
                "account_id": "acct_old",
            },
        )
        self._node(workflow, "model-1")["connections"] = {"connection_id": str(connection.pk)}
        workflow.save(update_fields=("definition",))

        def fake_urlopen(request, timeout=20):
            self.assertEqual(timeout, 20)
            if request.full_url == "https://auth.openai.com/oauth/token":
                self.assertEqual(request.get_method(), "POST")
                payload = parse_qs(request.data.decode("utf-8"))
                self.assertEqual(payload["grant_type"], ["refresh_token"])
                self.assertEqual(payload["refresh_token"], ["oauth-refresh-old"])
                self.assertEqual(payload["client_id"], ["client-openai-123"])
                self.assertEqual(payload["client_secret"], ["sk-test-client-secret"])
                return _FakeJsonResponse(
                    {
                        "access_token": "oauth-access-new",
                        "refresh_token": "oauth-refresh-new",
                        "expires_in": 3600,
                        "account_id": "acct_new",
                    }
                )
            self.assertEqual(request.full_url, "https://api.openai.com/v1/chat/completions")
            self.assertEqual(request.headers["Authorization"], "Bearer oauth-access-new")
            body = loads(request.data.decode("utf-8"))
            self.assertEqual(body["messages"][0]["content"], "Review T-88")
            return _FakeJsonResponse(
                {
                    "id": "chatcmpl-oauth-2",
                    "model": "gpt-4.1-mini",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": "Review T-88"},
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
                }
            )

        with patch("automation.tools.base.urlopen", side_effect=fake_urlopen):
            run = execute_workflow(workflow, input_data={"ticket_id": "T-88"})

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.output_data["response"], "Completed Review T-88")
        state.refresh_from_db()
        self.assertEqual(state.state_values["access_token"], "oauth-access-new")
        self.assertEqual(state.state_values["refresh_token"], "oauth-refresh-new")
        self.assertEqual(state.state_values["account_id"], "acct_new")
        self.assertIsNotNone(state.last_refreshed)

    def test_execute_workflow_rejects_legacy_agent_instructions_field(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="legacy agent instructions",
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
                        "label": "Draft",
                        "config": {
                            "instructions": "Review {{ trigger.payload.ticket_id }}",
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
            },
        )
        self._attach_openai_connection(workflow)

        run = execute_workflow(workflow, input_data={"ticket_id": "T-42"})

        self.assertEqual(run.status, "failed")
        self.assertIn("config.template", run.error)

    def test_execute_workflow_runs_v2_prometheus_query_with_connection(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="v2 prometheus runtime",
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
                        "type": "prometheus.action.query",
                        "label": "Prometheus query",
                        "config": {
                            "connection_id": "",
                            "query": "sum(rate(http_requests_total{job='{{ trigger.payload.job }}'}[5m]))",
                            "time": "1711798200",
                            "output_key": "prometheus.query",
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
        connection = self._create_connection(
            environment=self.environment,
            name="Primary Prometheus",
            integration_id="prometheus",
            connection_type="prometheus.api",
            data={
                "base_url": "https://prometheus.example.com",
                "bearer_token": "prom-secret",
            },
        )
        self._node(workflow, "tool-1")["connections"] = {"connection_id": str(connection.pk)}
        workflow.save(update_fields=("definition",))

        def fake_urlopen(request, timeout=20):
            self.assertEqual(timeout, 20)
            self.assertIn("/api/v1/query?", request.full_url)
            self.assertIn("query=sum%28rate%28http_requests_total%7Bjob%3D%27api%27%7D%5B5m%5D%29%29", request.full_url)
            self.assertIn("time=1711798200", request.full_url)
            self.assertEqual(request.headers["Authorization"], "Bearer prom-secret")
            return _FakeJsonResponse(
                {
                    "status": "success",
                    "data": {
                        "resultType": "vector",
                        "result": [{"metric": {"job": "api"}, "value": [1711798200, "4.2"]}],
                    },
                }
            )

        with patch("automation.tools.base.urlopen", side_effect=fake_urlopen):
            run = execute_workflow(workflow, input_data={"job": "api"})

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.step_results[1]["result"]["tool_name"], "prometheus_query")
        self.assertEqual(run.step_results[1]["result"]["result_count"], 1)
        self.assertEqual(run.context_data["prometheus"]["query"]["status"], "success")

    def test_execute_workflow_runs_v2_prometheus_query_with_typed_connection(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="v2 prometheus typed runtime",
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
                        "type": "prometheus.action.query",
                        "label": "Prometheus query",
                        "config": {
                            "connection_id": "",
                            "query": "sum(rate(http_requests_total{job='{{ trigger.payload.job }}'}[5m]))",
                            "time": "1711798200",
                            "output_key": "prometheus.query",
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
        connection = self._create_connection(
            environment=self.environment,
            name="Typed Prometheus",
            integration_id="prometheus",
            connection_type="prometheus.api",
            data={
                "base_url": "https://prometheus.example.com",
                "bearer_token": "prom-secret",
            },
        )
        self._node(workflow, "tool-1")["connections"] = {"connection_id": str(connection.pk)}
        workflow.save(update_fields=("definition",))

        def fake_urlopen(request, timeout=20):
            self.assertEqual(timeout, 20)
            self.assertIn("/api/v1/query?", request.full_url)
            self.assertIn("time=1711798200", request.full_url)
            self.assertEqual(request.headers["Authorization"], "Bearer prom-secret")
            return _FakeJsonResponse(
                {
                    "status": "success",
                    "data": {
                        "resultType": "vector",
                        "result": [{"metric": {"job": "api"}, "value": [1711798200, "4.2"]}],
                    },
                }
            )

        with patch("automation.tools.base.urlopen", side_effect=fake_urlopen):
            run = execute_workflow(workflow, input_data={"job": "api"})

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.step_results[1]["result"]["tool_name"], "prometheus_query")
        self.assertEqual(run.step_results[1]["result"]["result_count"], 1)
        self.assertEqual(run.context_data["prometheus"]["query"]["status"], "success")

    def test_execute_workflow_runs_v2_elasticsearch_search_with_connection(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="v2 elasticsearch runtime",
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
                        "type": "elasticsearch.action.search",
                        "label": "Elasticsearch search",
                        "config": {
                            "connection_id": "",
                            "index": "logs-*",
                            "auth_scheme": "ApiKey",
                            "query_json": "{\"query\": {\"term\": {\"service.keyword\": \"{{ trigger.payload.service }}\"}}}",
                            "size": 5,
                            "output_key": "elastic.search",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {
                            "value_path": "elastic.search",
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
        connection = self._create_connection(
            environment=self.environment,
            name="Primary Elasticsearch",
            integration_id="elasticsearch",
            connection_type="elasticsearch.api",
            data={
                "base_url": "https://elastic.example.com",
                "auth_token": "elastic-secret",
            },
        )
        self._node(workflow, "tool-1")["connections"] = {"connection_id": str(connection.pk)}
        workflow.save(update_fields=("definition",))

        def fake_urlopen(request, timeout=20):
            self.assertEqual(timeout, 20)
            self.assertEqual(request.full_url, "https://elastic.example.com/logs-*/_search")
            self.assertEqual(request.headers["Authorization"], "ApiKey elastic-secret")
            body = loads(request.data.decode("utf-8"))
            self.assertEqual(body["size"], 5)
            self.assertEqual(body["query"]["term"]["service.keyword"], "api")
            return _FakeJsonResponse(
                {
                    "took": 12,
                    "hits": {
                        "total": {"value": 1, "relation": "eq"},
                        "hits": [{"_id": "doc-1", "_source": {"service": "api"}}],
                    },
                    "aggregations": {"service_count": {"value": 1}},
                }
            )

        with patch("automation.tools.base.urlopen", side_effect=fake_urlopen):
            run = execute_workflow(workflow, input_data={"service": "api"})

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.step_results[1]["result"]["tool_name"], "elasticsearch_search")
        self.assertEqual(run.step_results[1]["result"]["hit_count"], 1)
        self.assertEqual(run.context_data["elastic"]["search"]["total"]["value"], 1)

    def test_execute_workflow_rejects_unsupported_node_types(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="unsupported node types",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "external.manualTrigger",
                        "label": "Manual",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {
                            "template": "mixed",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
                ],
            },
        )

        run = execute_workflow(workflow)

        self.assertEqual(run.status, "failed")
        self.assertIn('type "external.manualtrigger" is not supported', run.error.lower())

    def test_execute_workflow_runs_schedule_trigger_builtin(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="schedule trigger built-in",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "core.schedule_trigger",
                        "label": "Schedule Trigger",
                        "config": {
                            "cron": "0 */2 * * *",
                        },
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {
                            "template": "{{ trigger.type }} every {{ trigger.payload.interval|default:'manual' }}",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
                ],
            },
        )

        run = execute_workflow(workflow, input_data={"interval": "manual"})

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.step_results[0]["result"]["schedule"]["cron"], "0 */2 * * *")
        self.assertEqual(run.step_results[0]["type"], "core.schedule_trigger")

    def test_execute_workflow_runs_webhook_trigger_builtin(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="webhook trigger built-in",
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
                            "template": "{{ trigger.type }}:{{ trigger.payload.ticket_id }}",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
                ],
            },
        )

        run = execute_workflow(
            workflow,
            input_data={"ticket_id": "INC-321"},
            trigger_mode="core.webhook_trigger",
            trigger_metadata={"method": "POST"},
        )

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.step_results[0]["type"], "core.webhook_trigger")
        self.assertEqual(run.output_data["response"], "core.webhook_trigger:INC-321")

    def test_execute_workflow_uses_selected_trigger_node_from_metadata(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="multiple webhook triggers",
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
                        "label": "POST response",
                        "config": {
                            "template": "post:{{ trigger.meta.method }}",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-get",
                        "kind": "response",
                        "type": "core.response",
                        "label": "GET response",
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
        )

        run = execute_workflow(
            workflow,
            input_data={"ticket_id": "INC-654"},
            trigger_mode="core.webhook_trigger",
            trigger_metadata={"method": "GET", "trigger_node_id": "trigger-get"},
        )

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.step_results[0]["node_id"], "trigger-get")
        self.assertEqual(run.output_data["response"], "get:GET")

    def test_execute_workflow_runs_switch_builtin(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="switch built-in",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "core.manual_trigger",
                        "label": "Manual Trigger",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "switch-1",
                        "kind": "condition",
                        "type": "core.switch",
                        "label": "Switch",
                        "config": {
                            "mode": "rules",
                            "rules": {
                                "values": [
                                    {
                                        "leftPath": "trigger.payload.status",
                                        "operator": "equals",
                                        "rightValue": "queued",
                                    },
                                    {
                                        "leftPath": "trigger.payload.status",
                                        "operator": "equals",
                                        "rightValue": "running",
                                    },
                                ]
                            },
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-queued",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Queued",
                        "config": {
                            "template": "queued",
                        },
                        "position": {"x": 608, "y": 0},
                    },
                    {
                        "id": "response-running",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Running",
                        "config": {
                            "template": "running",
                        },
                        "position": {"x": 608, "y": 80},
                    },
                    {
                        "id": "response-other",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Other",
                        "config": {
                            "template": "other",
                        },
                        "position": {"x": 608, "y": 160},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "switch-1"},
                    {"id": "edge-2", "source": "switch-1", "sourcePort": "case_1", "target": "response-queued"},
                    {"id": "edge-3", "source": "switch-1", "sourcePort": "case_2", "target": "response-running"},
                    {"id": "edge-4", "source": "switch-1", "sourcePort": "fallback", "target": "response-other"},
                ],
            },
        )

        run = execute_workflow(workflow, input_data={"status": "running"})

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.output_data["response"], "running")
        self.assertEqual(run.step_results[1]["result"]["matched_case"], "case_2")

    def test_execute_workflow_runs_if_builtin_with_conditions_block(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="if built-in conditions block",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "core.manual_trigger",
                        "label": "Manual Trigger",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "if-1",
                        "kind": "condition",
                        "type": "core.if",
                        "label": "If",
                        "config": {
                            "combinator": "and",
                            "conditions": {
                                "conditions": [
                                    {
                                        "leftPath": "trigger.payload.status",
                                        "operator": "equals",
                                        "rightValue": "queued",
                                    },
                                    {
                                        "leftPath": "trigger.payload.priority",
                                        "operator": {"operation": "greater_than"},
                                        "rightValue": 1,
                                    },
                                ],
                                "options": {"ignoreCase": True},
                            },
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-true",
                        "kind": "response",
                        "type": "core.response",
                        "label": "True",
                        "config": {"template": "true"},
                        "position": {"x": 608, "y": 0},
                    },
                    {
                        "id": "response-false",
                        "kind": "response",
                        "type": "core.response",
                        "label": "False",
                        "config": {"template": "false"},
                        "position": {"x": 608, "y": 80},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "if-1"},
                    {"id": "edge-2", "source": "if-1", "sourcePort": "true", "target": "response-true"},
                    {"id": "edge-3", "source": "if-1", "sourcePort": "false", "target": "response-false"},
                ],
            },
        )

        run = execute_workflow(workflow, input_data={"status": "QUEUED", "priority": 2})

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.output_data["response"], "true")
        self.assertEqual(run.step_results[1]["result"]["condition_count"], 2)

    def test_execute_workflow_runs_switch_builtin_in_expression_mode(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="switch expression mode",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "core.manual_trigger",
                        "label": "Manual Trigger",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "switch-1",
                        "kind": "condition",
                        "type": "core.switch",
                        "label": "Switch",
                        "config": {
                            "mode": "expression",
                            "numberOutputs": 3,
                            "output": "{{ trigger.payload.target_index }}",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    *[
                        {
                            "id": f"response-{index}",
                            "kind": "response",
                            "type": "core.response",
                            "label": f"Response {index}",
                            "config": {"template": f"case-{index}"},
                            "position": {"x": 608, "y": index * 80},
                        }
                        for index in range(1, 4)
                    ],
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "switch-1"},
                    {"id": "edge-2", "source": "switch-1", "sourcePort": "case_1", "target": "response-1"},
                    {"id": "edge-3", "source": "switch-1", "sourcePort": "case_2", "target": "response-2"},
                    {"id": "edge-4", "source": "switch-1", "sourcePort": "case_3", "target": "response-3"},
                ],
            },
        )

        run = execute_workflow(workflow, input_data={"target_index": 2})

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.output_data["response"], "case-3")
        self.assertEqual(run.step_results[1]["result"]["output_index"], 2)

    def test_execute_workflow_runs_set_builtin_in_raw_json_mode(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="set raw json mode",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "core.manual_trigger",
                        "label": "Manual Trigger",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "set-1",
                        "kind": "tool",
                        "type": "core.set",
                        "label": "Set",
                        "config": {
                            "mode": "raw",
                            "output_key": "payload.snapshot",
                            "json_output": {
                                "ticket": "{{ trigger.payload.ticket_id }}",
                                "severity": "{{ trigger.payload.severity }}",
                            },
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {"value_path": "payload.snapshot"},
                        "position": {"x": 608, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "set-1"},
                    {"id": "edge-2", "source": "set-1", "target": "response-1"},
                ],
            },
        )

        run = execute_workflow(workflow, input_data={"ticket_id": "T-55", "severity": "high"})

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.output_data["response"]["ticket"], "T-55")
        self.assertEqual(run.output_data["response"]["severity"], "high")

    def test_execute_workflow_runs_stop_and_error_builtin(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="stop and error built-in",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "core.manual_trigger",
                        "label": "Manual Trigger",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "stop-1",
                        "kind": "condition",
                        "type": "core.stop_and_error",
                        "label": "Stop and Error",
                        "config": {
                            "message": "boom",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "stop-1"},
                ],
            },
        )

        run = execute_workflow(workflow)

        self.assertEqual(run.status, "failed")
        self.assertEqual(run.output_data["message"], "boom")
        self.assertEqual(run.step_results[1]["type"], "core.stop_and_error")

    def test_execute_workflow_runs_set_builtin_with_structured_manual_fields(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="set built-in structured manual fields",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "core.manual_trigger",
                        "label": "Manual Trigger",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "set-1",
                        "kind": "tool",
                        "type": "core.set",
                        "label": "Edit Fields",
                        "config": {
                            "mode": "manual",
                            "output_key": "payload.snapshot",
                            "fields": {
                                "values": [
                                    {"name": "ticket", "type": "stringValue", "stringValue": "{{ trigger.payload.ticket_id }}"},
                                    {"name": "severity_rank", "type": "numberValue", "numberValue": 2},
                                    {"name": "is_paged", "type": "booleanValue", "booleanValue": True},
                                    {"name": "labels", "type": "arrayValue", "arrayValue": ["ops", "incident"]},
                                    {"name": "meta", "type": "objectValue", "objectValue": {"service": "{{ trigger.payload.service }}"}},
                                ],
                            },
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {"value_path": "payload.snapshot"},
                        "position": {"x": 608, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "set-1"},
                    {"id": "edge-2", "source": "set-1", "target": "response-1"},
                ],
            },
        )

        run = execute_workflow(workflow, input_data={"ticket_id": "T-80", "service": "billing"})

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.output_data["response"]["ticket"], "T-80")
        self.assertEqual(run.output_data["response"]["severity_rank"], 2)
        self.assertEqual(run.output_data["response"]["is_paged"], True)
        self.assertEqual(run.output_data["response"]["labels"], ["ops", "incident"])
        self.assertEqual(run.output_data["response"]["meta"]["service"], "billing")

    def test_execute_workflow_runs_if_and_switch_with_structured_rules(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="if and switch structured rules",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "core.manual_trigger",
                        "label": "Manual Trigger",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "if-1",
                        "kind": "control",
                        "type": "core.if",
                        "label": "If",
                        "config": {
                            "combinator": "and",
                            "conditions": {
                                "conditions": [
                                    {
                                        "leftPath": "trigger.payload.environment",
                                        "operator": "equals",
                                        "rightValue": "production",
                                    },
                                ],
                            },
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "switch-1",
                        "kind": "control",
                        "type": "core.switch",
                        "label": "Switch",
                        "config": {
                            "mode": "rules",
                            "fallbackOutput": "extra",
                            "rules": {
                                "values": [
                                    {
                                        "leftPath": "trigger.payload.severity",
                                        "operator": "equals",
                                        "rightValue": "critical",
                                    },
                                    {
                                        "leftPath": "trigger.payload.severity",
                                        "operator": "equals",
                                        "rightValue": "high",
                                    },
                                ],
                            },
                        },
                        "position": {"x": 608, "y": 40},
                    },
                    {
                        "id": "critical-1",
                        "kind": "tool",
                        "type": "core.set",
                        "label": "Critical",
                        "config": {"mode": "raw", "output_key": "route", "json_output": '"critical"'},
                        "position": {"x": 896, "y": -80},
                    },
                    {
                        "id": "high-1",
                        "kind": "tool",
                        "type": "core.set",
                        "label": "High",
                        "config": {"mode": "raw", "output_key": "route", "json_output": '"high"'},
                        "position": {"x": 896, "y": 40},
                    },
                    {
                        "id": "fallback-1",
                        "kind": "tool",
                        "type": "core.set",
                        "label": "Fallback",
                        "config": {"mode": "raw", "output_key": "route", "json_output": '"fallback"'},
                        "position": {"x": 896, "y": 160},
                    },
                    {
                        "id": "stop-1",
                        "kind": "control",
                        "type": "core.stop_and_error",
                        "label": "Stop",
                        "config": {"message": "not production"},
                        "position": {"x": 608, "y": 160},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {"value_path": "route"},
                        "position": {"x": 1184, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "if-1"},
                    {"id": "edge-2", "source": "if-1", "sourcePort": "true", "target": "switch-1"},
                    {"id": "edge-3", "source": "if-1", "sourcePort": "false", "target": "stop-1"},
                    {"id": "edge-4", "source": "switch-1", "sourcePort": "case_1", "target": "critical-1"},
                    {"id": "edge-5", "source": "switch-1", "sourcePort": "case_2", "target": "high-1"},
                    {"id": "edge-6", "source": "switch-1", "sourcePort": "fallback", "target": "fallback-1"},
                    {"id": "edge-7", "source": "critical-1", "target": "response-1"},
                    {"id": "edge-8", "source": "high-1", "target": "response-1"},
                    {"id": "edge-9", "source": "fallback-1", "target": "response-1"},
                ],
            },
        )

        run = execute_workflow(
            workflow,
            input_data={"environment": "production", "severity": "high"},
        )

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.output_data["response"], "high")

    def test_execute_workflow_run_exposes_active_node_state_while_running(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Visible runtime progress",
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
                        "id": "set-1",
                        "kind": "tool",
                        "type": "core.set",
                        "label": "Set value",
                        "config": {
                            "mode": "raw",
                            "output_key": "draft",
                            "json_output": '"ready"',
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "core.response",
                        "label": "Done",
                        "config": {
                            "value_path": "draft",
                        },
                        "position": {"x": 608, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "set-1"},
                    {"id": "edge-2", "source": "set-1", "target": "response-1"},
                ],
            },
        )
        run = _initialize_workflow_run(
            workflow,
            input_data={"ticket_id": "T-99"},
            trigger_mode="manual",
            trigger_metadata={},
            actor=None,
            execution_mode=WorkflowRun.ExecutionModeChoices.WORKFLOW,
        )
        observed_scheduler_state = {}

        def delaying_execute_node(*args, **kwargs):
            node = kwargs["node"]
            if node["id"] == "trigger-1":
                observed_run = WorkflowRun.objects.get(pk=run.pk)
                observed_scheduler_state.update(observed_run.scheduler_state)
            return original_execute_node(*args, **kwargs)

        original_execute_node = __import__("automation.runtime", fromlist=["_execute_node"])._execute_node
        with patch("automation.runtime._execute_node", side_effect=delaying_execute_node):
            execute_workflow_run(WorkflowRun.objects.get(pk=run.pk))

        observed_run = WorkflowRun.objects.get(pk=run.pk)
        observed_run.refresh_from_db()
        self.assertEqual(observed_run.status, WorkflowRun.StatusChoices.SUCCEEDED)
        self.assertEqual(observed_scheduler_state["active_node_ids"], ["trigger-1"])
        self.assertEqual(observed_run.output_data["response"], "ready")
