import os
import subprocess
import tempfile
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
from automation.models import Secret, SecretGroup
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
        self._bind_secret(
            workflow=workflow,
            secret_name="OPENAI_API_KEY",
        )

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

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai"}, clear=False):
            with patch("automation.tools.base.urlopen", side_effect=fake_urlopen):
                run = execute_workflow(
                    workflow,
                    input_data={"ticket_id": "T-42"},
                )

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.output_data["response"], "Completed Review T-42")
        self.assertEqual(run.context_data["llm"]["response"]["text"], "Review T-42")
        self.assertEqual(run.step_count, 3)

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
        self._bind_secret(
            workflow=workflow,
            secret_name="OPENAI_API_KEY",
        )

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
                            "output_key": "branch.root",
                            "value": "fanout {{ trigger.payload.ticket_id }}",
                        },
                        "position": {"x": 320, "y": 60},
                    },
                    {
                        "id": "set-1",
                        "kind": "tool",
                        "type": "core.set",
                        "label": "Branch one",
                        "config": {
                            "output_key": "branch.one",
                            "value": "alpha",
                        },
                        "position": {"x": 608, "y": 0},
                    },
                    {
                        "id": "set-2",
                        "kind": "tool",
                        "type": "core.set",
                        "label": "Branch two",
                        "config": {
                            "output_key": "branch.two",
                            "value": "beta",
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
        self.assertEqual(
            [item["source_node_id"] for item in response_step.input_data["input_items"]],
            ["set-1", "set-2"],
        )
        self.assertEqual(
            [item["output"]["value"] for item in response_step.input_data["input_items"]],
            ["alpha", "beta"],
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
                            "output_key": "draft",
                            "value": "{{ trigger.payload.ticket_id }}",
                            "__input_modes": {
                                "value": "expression",
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
                            "output_key": "draft.result",
                            "value": "resolved",
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

        workflow.definition["nodes"][1]["config"]["template"] = "v2"
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
        self._bind_secret(
            workflow=workflow,
            secret_name="OPENAI_API_KEY",
        )

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai"}, clear=False):
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
                            "output_key": "tool.output",
                            "value": "hello",
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
                            "output_key": "context.value",
                            "value": "hello",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "if-1",
                        "kind": "condition",
                        "type": "core.if",
                        "label": "If",
                        "config": {
                            "path": "context.value",
                            "operator": "equals",
                            "right_value": "hello",
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
                            "output_key": "context.value",
                            "value": "hello",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "if-1",
                        "kind": "condition",
                        "type": "core.if",
                        "label": "If",
                        "config": {
                            "path": "context.value",
                            "operator": "equals",
                            "right_value": "hello",
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
        secret = self._bind_secret(
            workflow=workflow,
            secret_name="OPENAI_API_KEY",
        )
        connection = WorkflowConnection.objects.create(
            environment=self.environment,
            name="Primary OpenAI",
            integration_id="openai",
            connection_type="openai.api",
            secret_group=secret.secret_group,
            field_values={
                "base_url": "https://api.openai.com/v1",
                "api_key": {"source": "secret", "secret_name": secret.name},
            },
        )
        workflow.definition["nodes"][2]["config"]["connection_id"] = str(connection.pk)
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

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai"}, clear=False):
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
        secret = self._bind_secret(
            workflow=workflow,
            secret_name="OPENAI_API_KEY",
        )
        connection = WorkflowConnection.objects.create(
            environment=self.environment,
            name="Typed OpenAI",
            integration_id="openai",
            connection_type="openai.api",
            secret_group=secret.secret_group,
            field_values={
                "base_url": "https://api.openai.com/v1",
                "api_key": {"source": "secret", "secret_name": secret.name},
            },
        )
        workflow.definition["nodes"][2]["config"]["connection_id"] = str(connection.pk)
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

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai"}, clear=False):
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
        connection = WorkflowConnection.objects.create(
            environment=self.environment,
            name="OpenAI OAuth",
            integration_id="openai",
            connection_type="openai.api",
            field_values={
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
        workflow.definition["nodes"][2]["config"]["connection_id"] = str(connection.pk)
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
        secret = self._bind_secret(
            workflow=workflow,
            secret_name="OPENAI_OAUTH_CLIENT_SECRET",
        )
        connection = WorkflowConnection.objects.create(
            environment=self.environment,
            name="OpenAI OAuth Refresh",
            integration_id="openai",
            connection_type="openai.api",
            secret_group=secret.secret_group,
            field_values={
                "auth_mode": "oauth2_authorization_code",
                "base_url": "https://api.openai.com/v1",
                "oauth_client_id": "client-openai-123",
                "oauth_client_secret": {"source": "secret", "secret_name": secret.name},
                "oauth_token_url": "https://auth.openai.com/oauth/token",
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
        workflow.definition["nodes"][2]["config"]["connection_id"] = str(connection.pk)
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

        with patch.dict(os.environ, {"OPENAI_OAUTH_CLIENT_SECRET": "sk-test-client-secret"}, clear=False):
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
        secret = self._bind_secret(
            workflow=workflow,
            secret_name="PROMETHEUS_API_TOKEN",
        )
        connection = WorkflowConnection.objects.create(
            environment=self.environment,
            name="Primary Prometheus",
            integration_id="prometheus",
            connection_type="prometheus.api",
            secret_group=secret.secret_group,
            field_values={
                "base_url": "https://prometheus.example.com",
                "bearer_token": {"source": "secret", "secret_name": secret.name},
            },
        )
        workflow.definition["nodes"][1]["config"]["connection_id"] = str(connection.pk)
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

        with patch.dict(os.environ, {"PROMETHEUS_API_TOKEN": "prom-secret"}, clear=False):
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
        secret = self._bind_secret(
            workflow=workflow,
            secret_name="PROMETHEUS_API_TOKEN",
        )
        connection = WorkflowConnection.objects.create(
            environment=self.environment,
            name="Typed Prometheus",
            integration_id="prometheus",
            connection_type="prometheus.api",
            secret_group=secret.secret_group,
            field_values={
                "base_url": "https://prometheus.example.com",
                "bearer_token": {"source": "secret", "secret_name": secret.name},
            },
        )
        workflow.definition["nodes"][1]["config"]["connection_id"] = str(connection.pk)
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

        with patch.dict(os.environ, {"PROMETHEUS_API_TOKEN": "prom-secret"}, clear=False):
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
        secret = self._bind_secret(
            workflow=workflow,
            secret_name="ELASTICSEARCH_API_KEY",
        )
        connection = WorkflowConnection.objects.create(
            environment=self.environment,
            name="Primary Elasticsearch",
            integration_id="elasticsearch",
            connection_type="elasticsearch.api",
            secret_group=secret.secret_group,
            field_values={
                "base_url": "https://elastic.example.com",
                "auth_token": {"source": "secret", "secret_name": secret.name},
            },
        )
        workflow.definition["nodes"][1]["config"]["connection_id"] = str(connection.pk)
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

        with patch.dict(os.environ, {"ELASTICSEARCH_API_KEY": "elastic-secret"}, clear=False):
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
                        "type": "n8n-nodes-base.manualTrigger",
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
        self.assertIn('type "n8n-nodes-base.manualtrigger" is not supported', run.error.lower())

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
                            "path": "trigger.payload.status",
                            "case_1_value": "queued",
                            "case_2_value": "running",
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
                            "output_key": "draft",
                            "value": "ready",
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
