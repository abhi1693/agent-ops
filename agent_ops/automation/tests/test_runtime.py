import os
import subprocess
from json import loads
from unittest.mock import patch

from django.test import TestCase

from automation.models import Workflow
from automation.runtime import execute_workflow
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
                        "type": "n8n-nodes-base.manualTrigger",
                        "label": "Manual",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "agent-1",
                        "kind": "agent",
                        "type": "agent",
                        "label": "Draft",
                        "config": {
                            "template": "Review {{ trigger.payload.ticket_id }}",
                            "secret_name": "OPENAI_API_KEY",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "response",
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

    def test_execute_workflow_runs_agent_with_connected_chat_model_and_mcp_tool(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Connected agent runtime",
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
                        "label": "AI Agent",
                        "config": {
                            "template": "What is the weather in {{ trigger.payload.city }}?",
                            "secret_name": "OPENAI_API_KEY",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "response",
                        "label": "Done",
                        "config": {
                            "template": "Completed {{ llm.response.text }}",
                        },
                        "position": {"x": 608, "y": 40},
                    },
                    {
                        "id": "model-1",
                        "kind": "tool",
                        "type": "tool.openai_chat_model",
                        "label": "OpenAI chat model",
                        "config": {
                            "base_url": "https://api.openai.com/v1",
                            "model": "gpt-4.1-mini",
                            "secret_name": "OPENAI_API_KEY",
                        },
                        "position": {"x": 240, "y": 240},
                    },
                    {
                        "id": "tool-1",
                        "kind": "tool",
                        "type": "tool.mcp_server",
                        "label": "Weather tool",
                        "config": {
                            "output_key": "weather.result",
                            "server_url": "https://mcp.example.com/mcp",
                            "remote_tool_name": "weather_current",
                            "secret_name": "MCP_API_TOKEN",
                        },
                        "position": {"x": 400, "y": 240},
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
        self._bind_secret(
            workflow=workflow,
            secret_name="OPENAI_API_KEY",
        )
        self._bind_secret(
            workflow=workflow,
            secret_name="MCP_API_TOKEN",
        )

        openai_call_count = {"value": 0}

        def fake_openai_urlopen(request, timeout=20):
            self.assertEqual(timeout, 20)
            self.assertEqual(request.full_url, "https://api.openai.com/v1/chat/completions")
            self.assertEqual(request.headers["Authorization"], "Bearer sk-test-openai")
            body = loads(request.data.decode("utf-8"))
            openai_call_count["value"] += 1

            if openai_call_count["value"] == 1:
                self.assertEqual(body["messages"][0]["role"], "user")
                self.assertEqual(body["messages"][0]["content"], "What is the weather in Bengaluru?")
                self.assertEqual(body["tools"][0]["function"]["name"], "weather_current")
                return _FakeJsonResponse(
                    {
                        "id": "chatcmpl-100",
                        "model": "gpt-4.1-mini",
                        "choices": [
                            {
                                "finish_reason": "tool_calls",
                                "message": {
                                    "role": "assistant",
                                    "tool_calls": [
                                        {
                                            "id": "call-weather-1",
                                            "type": "function",
                                            "function": {
                                                "name": "weather_current",
                                                "arguments": "{\"location\": \"Bengaluru\"}",
                                            },
                                        }
                                    ],
                                },
                            }
                        ],
                        "usage": {"prompt_tokens": 40, "completion_tokens": 8, "total_tokens": 48},
                    }
                )

            self.assertEqual(openai_call_count["value"], 2)
            self.assertEqual(body["messages"][0]["role"], "user")
            self.assertEqual(body["messages"][1]["role"], "assistant")
            self.assertEqual(body["messages"][2]["role"], "tool")
            self.assertIn("31C", body["messages"][2]["content"])
            return _FakeJsonResponse(
                {
                    "id": "chatcmpl-101",
                    "model": "gpt-4.1-mini",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "content": "The weather in Bengaluru is 31C.",
                            },
                        }
                    ],
                    "usage": {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60},
                }
            )

        def fake_mcp_urlopen(request, timeout=30):
            self.assertEqual(timeout, 30)
            self.assertEqual(request.full_url, "https://mcp.example.com/mcp")
            self.assertEqual(request.headers["Authorization"], "Bearer mcp-secret")
            if request.method == "DELETE":
                return _FakeJsonResponse({}, status=200, raw_body=b"")

            raw_body = loads(request.data.decode("utf-8")) if request.data else {}
            method = raw_body.get("method")
            if method == "initialize":
                return _FakeJsonResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": raw_body["id"],
                        "result": {
                            "protocolVersion": "2025-11-25",
                        },
                    },
                    headers={"MCP-Session-Id": "session-1"},
                )
            if method == "notifications/initialized":
                return _FakeJsonResponse({}, status=202, raw_body=b"")
            if method == "tools/list":
                return _FakeJsonResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": raw_body["id"],
                        "result": {
                            "tools": [
                                {
                                    "name": "weather_current",
                                    "description": "Get the current weather for a city.",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {
                                            "location": {"type": "string"},
                                        },
                                        "required": ["location"],
                                    },
                                }
                            ]
                        },
                    }
                )
            if method == "tools/call":
                self.assertEqual(raw_body["params"]["name"], "weather_current")
                self.assertEqual(raw_body["params"]["arguments"], {"location": "Bengaluru"})
                return _FakeJsonResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": raw_body["id"],
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Weather for Bengaluru: 31C and sunny.",
                                }
                            ],
                            "structuredContent": {
                                "location": "Bengaluru",
                                "temperature_c": 31,
                            },
                            "isError": False,
                        },
                    }
                )

            raise AssertionError(f"Unexpected MCP method: {method}")

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai", "MCP_API_TOKEN": "mcp-secret"}, clear=False):
            with patch("automation.tools.base.urlopen", side_effect=fake_openai_urlopen):
                with patch("automation.nodes.apps.integrations.mcp_server.node.urlopen", side_effect=fake_mcp_urlopen):
                    run = execute_workflow(
                        workflow,
                        input_data={"city": "Bengaluru"},
                    )

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.output_data["response"], "Completed The weather in Bengaluru is 31C.")
        self.assertEqual(run.context_data["llm"]["response"]["text"], "The weather in Bengaluru is 31C.")
        self.assertEqual(len(run.context_data["llm"]["response"]["tool_runs"]), 1)
        self.assertEqual(run.context_data["llm"]["response"]["tool_runs"][0]["remote_tool_name"], "weather_current")
        self.assertEqual(run.step_count, 3)

    def test_execute_workflow_runs_agent_with_generic_attached_tool(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Connected agent generic tool runtime",
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
                        "label": "AI Agent",
                        "config": {
                            "template": "Summarize the city briefing for {{ trigger.payload.city }}.",
                            "secret_name": "OPENAI_API_KEY",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "response",
                        "label": "Done",
                        "config": {
                            "template": "Completed {{ llm.response.text }}",
                        },
                        "position": {"x": 608, "y": 40},
                    },
                    {
                        "id": "model-1",
                        "kind": "tool",
                        "type": "tool.openai_chat_model",
                        "label": "OpenAI chat model",
                        "config": {
                            "base_url": "https://api.openai.com/v1",
                            "model": "gpt-4.1-mini",
                            "secret_name": "OPENAI_API_KEY",
                        },
                        "position": {"x": 240, "y": 240},
                    },
                    {
                        "id": "tool-1",
                        "kind": "tool",
                        "type": "tool.template",
                        "label": "render_template",
                        "config": {
                            "output_key": "template.result",
                        },
                        "position": {"x": 400, "y": 240},
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
        self._bind_secret(
            workflow=workflow,
            secret_name="OPENAI_API_KEY",
        )

        openai_call_count = {"value": 0}

        def fake_openai_urlopen(request, timeout=20):
            self.assertEqual(timeout, 20)
            self.assertEqual(request.full_url, "https://api.openai.com/v1/chat/completions")
            self.assertEqual(request.headers["Authorization"], "Bearer sk-test-openai")
            body = loads(request.data.decode("utf-8"))
            openai_call_count["value"] += 1

            if openai_call_count["value"] == 1:
                self.assertEqual(body["messages"][0]["role"], "user")
                self.assertEqual(body["tools"][0]["function"]["name"], "render_template")
                self.assertIn("template", body["tools"][0]["function"]["parameters"]["properties"])
                return _FakeJsonResponse(
                    {
                        "id": "chatcmpl-200",
                        "model": "gpt-4.1-mini",
                        "choices": [
                            {
                                "finish_reason": "tool_calls",
                                "message": {
                                    "role": "assistant",
                                    "tool_calls": [
                                        {
                                            "id": "call-template-1",
                                            "type": "function",
                                            "function": {
                                                "name": "render_template",
                                                "arguments": "{\"template\": \"City briefing: Bengaluru is stable.\"}",
                                            },
                                        }
                                    ],
                                },
                            }
                        ],
                        "usage": {"prompt_tokens": 40, "completion_tokens": 8, "total_tokens": 48},
                    }
                )

            self.assertEqual(openai_call_count["value"], 2)
            self.assertEqual(body["messages"][2]["role"], "tool")
            self.assertIn("Bengaluru is stable", body["messages"][2]["content"])
            return _FakeJsonResponse(
                {
                    "id": "chatcmpl-201",
                    "model": "gpt-4.1-mini",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "content": "Bengaluru is stable.",
                            },
                        }
                    ],
                    "usage": {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60},
                }
            )

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai"}, clear=False):
            with patch("automation.tools.base.urlopen", side_effect=fake_openai_urlopen):
                run = execute_workflow(
                    workflow,
                    input_data={"city": "Bengaluru"},
                )

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.output_data["response"], "Completed Bengaluru is stable.")
        self.assertEqual(run.context_data["llm"]["response"]["text"], "Bengaluru is stable.")
        self.assertEqual(len(run.context_data["llm"]["response"]["tool_runs"]), 1)
        self.assertEqual(run.context_data["llm"]["response"]["tool_runs"][0]["remote_tool_name"], "template")
        self.assertEqual(
            run.context_data["llm"]["response"]["tool_runs"][0]["result"]["tool_name"],
            "template",
        )
        self.assertEqual(run.step_count, 3)

    def test_execute_workflow_runs_n8n_style_builtins_end_to_end(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="n8n-style built-ins",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "n8n-nodes-base.manualTrigger",
                        "label": "Manual Trigger",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "set-1",
                        "kind": "tool",
                        "type": "n8n-nodes-base.set",
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
                        "type": "n8n-nodes-base.if",
                        "label": "If",
                        "config": {
                            "path": "context.value",
                            "operator": "equals",
                            "right_value": "hello",
                            "true_target": "response-hello",
                            "false_target": "response-other",
                        },
                        "position": {"x": 608, "y": 40},
                    },
                    {
                        "id": "response-hello",
                        "kind": "response",
                        "type": "response",
                        "label": "Matched",
                        "config": {
                            "value_path": "context.value",
                        },
                        "position": {"x": 896, "y": 0},
                    },
                    {
                        "id": "response-other",
                        "kind": "response",
                        "type": "response",
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
                    {"id": "edge-3", "source": "if-1", "target": "response-hello"},
                    {"id": "edge-4", "source": "if-1", "target": "response-other"},
                ],
            },
        )

        run = execute_workflow(workflow)

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.output_data["response"], "hello")
        self.assertEqual(run.context_data["context"]["value"], "hello")
        self.assertEqual(run.step_count, 4)

    def test_execute_workflow_runs_schedule_trigger_builtin(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="schedule trigger built-in",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "n8n-nodes-base.scheduleTrigger",
                        "label": "Schedule Trigger",
                        "config": {
                            "mode": "interval",
                            "interval_unit": "hours",
                            "interval_value": "2",
                        },
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "response",
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
        self.assertEqual(run.step_results[0]["result"]["schedule"]["interval_unit"], "hours")
        self.assertEqual(run.step_results[0]["type"], "n8n-nodes-base.scheduleTrigger")

    def test_execute_workflow_runs_switch_builtin(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="switch built-in",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "n8n-nodes-base.manualTrigger",
                        "label": "Manual Trigger",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "switch-1",
                        "kind": "condition",
                        "type": "n8n-nodes-base.switch",
                        "label": "Switch",
                        "config": {
                            "path": "trigger.payload.status",
                            "case_1_value": "queued",
                            "case_1_target": "response-queued",
                            "case_2_value": "running",
                            "case_2_target": "response-running",
                            "fallback_target": "response-other",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-queued",
                        "kind": "response",
                        "type": "response",
                        "label": "Queued",
                        "config": {
                            "template": "queued",
                        },
                        "position": {"x": 608, "y": 0},
                    },
                    {
                        "id": "response-running",
                        "kind": "response",
                        "type": "response",
                        "label": "Running",
                        "config": {
                            "template": "running",
                        },
                        "position": {"x": 608, "y": 80},
                    },
                    {
                        "id": "response-other",
                        "kind": "response",
                        "type": "response",
                        "label": "Other",
                        "config": {
                            "template": "other",
                        },
                        "position": {"x": 608, "y": 160},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "switch-1"},
                    {"id": "edge-2", "source": "switch-1", "target": "response-queued"},
                    {"id": "edge-3", "source": "switch-1", "target": "response-running"},
                    {"id": "edge-4", "source": "switch-1", "target": "response-other"},
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
                        "type": "n8n-nodes-base.manualTrigger",
                        "label": "Manual Trigger",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "stop-1",
                        "kind": "response",
                        "type": "n8n-nodes-base.stopAndError",
                        "label": "Stop and Error",
                        "config": {
                            "error_type": "errorMessage",
                            "error_message": "boom",
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
        self.assertEqual(run.output_data["response"]["message"], "boom")
        self.assertEqual(run.step_results[1]["type"], "n8n-nodes-base.stopAndError")

    def test_execute_workflow_redacts_secret_values_from_persisted_run_data(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Secret-backed runtime",
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
                        "type": "tool.secret",
                        "label": "Resolve key",
                        "config": {
                            "secret_name": "OPENAI_API_KEY",
                            "output_key": "credentials.openai",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "response",
                        "label": "Done",
                        "config": {
                            "template": "Resolved {{ credentials.openai }}",
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
        self._bind_secret(
            workflow=workflow,
            secret_name="OPENAI_API_KEY",
        )

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-secret"}, clear=False):
            run = execute_workflow(workflow)

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.context_data["credentials"]["openai"], "[redacted secret]")
        self.assertEqual(run.output_data["response"], "Resolved [redacted secret]")
        self.assertEqual(
            run.step_results[1]["result"]["secret"],
            {
                "name": "OPENAI_API_KEY",
                "provider": "environment-variable",
                "secret_group": workflow.secret_group.name,
            },
        )
        self.assertEqual(run.step_results[1]["result"]["tool_name"], "secret")

    def test_execute_workflow_rejects_unconfigured_tool_nodes(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Unconfigured tool runtime",
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
                        "label": "Unconfigured",
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "label": "Done",
                        "config": {
                            "template": "should not run",
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

        run = execute_workflow(workflow)

        self.assertEqual(run.status, "failed")
        self.assertEqual(run.error, 'definition: Node "tool-1" must define a supported type.')
        self.assertEqual(run.step_results, [])

        self.assertEqual(run.step_results, [])

    def test_execute_workflow_resolves_tool_auth_from_workflow_secret_group(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Grouped Prometheus runtime",
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
                        "type": "tool.prometheus_query",
                        "label": "Prometheus query",
                        "config": {
                            "base_url": "https://prometheus.example.com",
                            "query": "up{job='{{ trigger.payload.job }}'}",
                            "output_key": "prometheus.query",
                            "secret_name": "PROMETHEUS_API_TOKEN",
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
        self._bind_secret(
            workflow=workflow,
            secret_name="PROMETHEUS_API_TOKEN",
        )

        def fake_urlopen(request, timeout=20):
            self.assertEqual(timeout, 20)
            self.assertEqual(request.headers["Authorization"], "Bearer prom-secret")
            self.assertIn("/api/v1/query?", request.full_url)
            self.assertIn("query=up%7Bjob%3D%27api%27%7D", request.full_url)
            return _FakeJsonResponse(
                {
                    "status": "success",
                    "data": {
                        "resultType": "vector",
                        "result": [{"metric": {"job": "api"}, "value": [1711798200, "1"]}],
                    },
                }
            )

        with patch.dict(os.environ, {"PROMETHEUS_API_TOKEN": "prom-secret"}, clear=False):
            with patch("automation.tools.base.urlopen", side_effect=fake_urlopen):
                run = execute_workflow(workflow, input_data={"job": "api"})

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.output_data["response"]["status"], "success")
        self.assertEqual(run.step_results[1]["result"]["tool_name"], "prometheus_query")

    def test_execute_workflow_runs_local_kubectl_binary(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="kubectl workflow",
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
                        "type": "tool.kubectl",
                        "label": "kubectl",
                        "config": {
                            "output_key": "kubectl.result",
                            "command": "kubectl get pods -o json",
                            "output_format": "json",
                            "context_name": "prod-cluster",
                            "namespace": "payments",
                            "timeout_seconds": 15,
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "response",
                        "label": "Done",
                        "config": {
                            "value_path": "kubectl.result",
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

        expected_stdout = '{"items":[{"metadata":{"name":"api-0"}}]}\n'

        def fake_run(argv, check, capture_output, text, timeout):
            self.assertEqual(
                argv,
                [
                    "/usr/local/bin/kubectl",
                    "--context",
                    "prod-cluster",
                    "--namespace",
                    "payments",
                    "get",
                    "pods",
                    "-o",
                    "json",
                ],
            )
            self.assertFalse(check)
            self.assertTrue(capture_output)
            self.assertTrue(text)
            self.assertEqual(timeout, 15)
            return subprocess.CompletedProcess(argv, 0, stdout=expected_stdout, stderr="")

        with patch("automation.nodes.apps.infrastructure.kubectl.node.shutil.which", return_value="/usr/local/bin/kubectl"):
            with patch("automation.nodes.apps.infrastructure.kubectl.node.subprocess.run", side_effect=fake_run):
                run = execute_workflow(workflow)

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.output_data["response"]["output_format"], "json")
        self.assertEqual(run.output_data["response"]["data"]["items"][0]["metadata"]["name"], "api-0")
        self.assertEqual(run.step_results[1]["result"]["tool_name"], "kubectl")
        self.assertEqual(run.step_results[1]["result"]["item_count"], 1)

    def test_execute_workflow_calls_mcp_server_tool(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="MCP workflow",
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
                            "arguments_json": '{"location": "{{ trigger.payload.location }}", "units": "imperial"}',
                            "headers_json": '{"X-Tenant": "ops"}',
                            "output_key": "mcp.result",
                            "secret_name": "MCP_API_TOKEN",
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
        self._bind_secret(
            workflow=workflow,
            secret_name="MCP_API_TOKEN",
        )

        def fake_urlopen(request, timeout=20):
            body = loads(request.data.decode("utf-8")) if request.data else None
            self.assertEqual(timeout, 30)
            self.assertEqual(request.full_url, "https://mcp.example.com/mcp")
            self.assertEqual(request.headers["Accept"], "application/json, text/event-stream")

            if request.get_method() == "POST" and body["method"] == "initialize":
                self.assertEqual(body["params"]["protocolVersion"], "2025-11-25")
                self.assertEqual(body["params"]["clientInfo"]["name"], "agent-ops-workflow")
                self.assertEqual(request.headers["Authorization"], "Bearer mcp-secret")
                self.assertEqual(request.headers["X-tenant"], "ops")
                return _FakeJsonResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {
                            "protocolVersion": "2025-11-25",
                            "capabilities": {"tools": {}},
                            "serverInfo": {"name": "weather-server", "version": "1.0.0"},
                        },
                    },
                    headers={"MCP-Session-Id": "session-123"},
                )

            if request.get_method() == "POST" and body["method"] == "notifications/initialized":
                self.assertEqual(request.headers["Mcp-protocol-version"], "2025-11-25")
                self.assertEqual(request.headers["Mcp-session-id"], "session-123")
                return _FakeJsonResponse(None, status=202, raw_body=b"")

            if request.get_method() == "POST" and body["method"] == "tools/call":
                self.assertEqual(request.headers["Mcp-protocol-version"], "2025-11-25")
                self.assertEqual(request.headers["Mcp-session-id"], "session-123")
                self.assertEqual(body["params"]["name"], "weather_current")
                self.assertEqual(
                    body["params"]["arguments"],
                    {"location": "San Francisco", "units": "imperial"},
                )
                return _FakeJsonResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "result": {
                            "content": [{"type": "text", "text": "72F and sunny"}],
                            "structuredContent": {"temperature_f": 72, "conditions": "sunny"},
                        },
                    }
                )

            if request.get_method() == "DELETE":
                self.assertEqual(request.headers["Mcp-protocol-version"], "2025-11-25")
                self.assertEqual(request.headers["Mcp-session-id"], "session-123")
                return _FakeJsonResponse(None, status=204, raw_body=b"")

            self.fail(f"Unexpected MCP request: {request.get_method()} {body}")

        with patch.dict(os.environ, {"MCP_API_TOKEN": "mcp-secret"}, clear=False):
            with patch("automation.nodes.apps.integrations.mcp_server.node.urlopen", side_effect=fake_urlopen):
                run = execute_workflow(workflow, input_data={"location": "San Francisco"})

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.step_results[1]["result"]["tool_name"], "mcp_server")
        self.assertEqual(run.step_results[1]["result"]["remote_tool_name"], "weather_current")
        self.assertEqual(run.output_data["response"]["text"], "72F and sunny")
        self.assertEqual(run.output_data["response"]["structured_content"]["temperature_f"], 72)
        self.assertFalse(run.output_data["response"]["is_error"])

    def test_execute_workflow_calls_mcp_server_tool_from_sse_response(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="MCP SSE workflow",
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
                            "remote_tool_name": "health_check",
                            "arguments_json": "{}",
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

        sse_payload = (
            'data: {"jsonrpc":"2.0","method":"notifications/message","params":{"level":"info"}}\n'
            "\n"
            'data: {"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"ok"}],'
            '"structuredContent":{"ok":true}}}\n'
            "\n"
        ).encode("utf-8")

        def fake_urlopen(request, timeout=20):
            body = loads(request.data.decode("utf-8")) if request.data else None
            self.assertEqual(timeout, 30)

            if request.get_method() == "POST" and body["method"] == "initialize":
                return _FakeJsonResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {
                            "protocolVersion": "2025-11-25",
                            "capabilities": {"tools": {}},
                            "serverInfo": {"name": "health-server", "version": "1.0.0"},
                        },
                    },
                    headers={"MCP-Session-Id": "session-sse"},
                )

            if request.get_method() == "POST" and body["method"] == "notifications/initialized":
                return _FakeJsonResponse(None, status=202, raw_body=b"")

            if request.get_method() == "POST" and body["method"] == "tools/call":
                return _FakeJsonResponse(
                    None,
                    content_type="text/event-stream",
                    raw_body=sse_payload,
                )

            if request.get_method() == "DELETE":
                return _FakeJsonResponse(None, status=204, raw_body=b"")

            self.fail(f"Unexpected MCP request: {request.get_method()} {body}")

        with patch("automation.nodes.apps.integrations.mcp_server.node.urlopen", side_effect=fake_urlopen):
            run = execute_workflow(workflow)

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.output_data["response"]["text"], "ok")
        self.assertTrue(run.output_data["response"]["structured_content"]["ok"])

    def test_execute_workflow_rejects_rendered_external_url_with_embedded_credentials(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Invalid rendered URL workflow",
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
                        "type": "tool.prometheus_query",
                        "label": "Prometheus query",
                        "config": {
                            "base_url": "https://{{ trigger.payload.base_url }}",
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

        run = execute_workflow(
            workflow,
            input_data={"base_url": "operator:secret@prometheus.example.com"},
        )

        self.assertEqual(run.status, "failed")
        self.assertIn("cannot render a URL with embedded credentials", run.error)

    def test_execute_workflow_queries_prometheus_directly(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Prometheus workflow",
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
                        "type": "tool.prometheus_query",
                        "label": "Prometheus query",
                        "config": {
                            "base_url": "https://prometheus.example.com",
                            "query": "sum(rate(http_requests_total{job='{{ trigger.payload.job }}'}[5m]))",
                            "time": "1711798200",
                            "output_key": "prometheus.query",
                            "secret_name": "PROMETHEUS_API_TOKEN",
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
        self._bind_secret(
            workflow=workflow,
            secret_name="PROMETHEUS_API_TOKEN",
        )

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

    def test_execute_workflow_searches_elasticsearch(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Elasticsearch workflow",
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
                        "type": "tool.elasticsearch_search",
                        "label": "Elasticsearch search",
                        "config": {
                            "base_url": "https://elastic.example.com",
                            "index": "logs-*",
                            "auth_scheme": "ApiKey",
                            "query_json": "{\"size\": 5, \"query\": {\"term\": {\"service.keyword\": \"{{ trigger.payload.service }}\"}}}",
                            "output_key": "elastic.search",
                            "secret_name": "ELASTICSEARCH_API_KEY",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "response",
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
        self._bind_secret(
            workflow=workflow,
            secret_name="ELASTICSEARCH_API_KEY",
        )

        def fake_urlopen(request, timeout=20):
            self.assertEqual(timeout, 20)
            self.assertEqual(request.full_url, "https://elastic.example.com/logs-*/_search")
            self.assertEqual(request.headers["Authorization"], "ApiKey elastic-secret")
            body = loads(request.data.decode("utf-8"))
            self.assertEqual(body["size"], 5)
            self.assertEqual(body["query"]["term"]["service.keyword"], "payments-api")
            return _FakeJsonResponse(
                {
                    "took": 12,
                    "hits": {
                        "total": {"value": 2, "relation": "eq"},
                        "hits": [
                            {"_id": "doc-1", "_source": {"message": "first"}},
                            {"_id": "doc-2", "_source": {"message": "second"}},
                        ],
                    },
                    "aggregations": {"levels": {"buckets": [{"key": "error", "doc_count": 2}]}},
                }
            )

        with patch.dict(os.environ, {"ELASTICSEARCH_API_KEY": "elastic-secret"}, clear=False):
            with patch("automation.tools.base.urlopen", side_effect=fake_urlopen):
                run = execute_workflow(workflow, input_data={"service": "payments-api"})

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.step_results[1]["result"]["tool_name"], "elasticsearch_search")
        self.assertEqual(run.step_results[1]["result"]["hit_count"], 2)
        self.assertEqual(run.context_data["elastic"]["search"]["total"]["value"], 2)

    def test_execute_workflow_fails_when_configured_elasticsearch_secret_is_missing_from_group(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Elasticsearch missing secret ref",
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
                        "type": "tool.elasticsearch_search",
                        "label": "Elasticsearch search",
                        "config": {
                            "base_url": "https://elastic.example.com",
                            "index": "logs-*",
                            "auth_scheme": "ApiKey",
                            "query_json": "{\"size\": 1}",
                            "output_key": "elastic.search",
                            "secret_name": "ES_API_KEY",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "tool-1"},
                ],
            },
        )
        self._bind_secret(
            workflow=workflow,
            secret_name="api-key",
            variable_name="ES_API_KEY",
        )

        with patch("automation.tools.base.urlopen") as mocked_urlopen:
            run = execute_workflow(workflow, input_data={})

        self.assertEqual(run.status, "failed")
        self.assertIn('does not include secret "ES_API_KEY"', run.error)
        mocked_urlopen.assert_not_called()

    def test_execute_workflow_calls_openai_compatible_chat_from_agent_node(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="LLM workflow",
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
                        "label": "OpenAI-compatible chat",
                        "config": {
                            "base_url": "https://llm.example.com/v1",
                            "model": "gpt-4.1-mini",
                            "secret_name": "OPENAI_COMPATIBLE_API_KEY",
                            "system_prompt": "You are an incident triage assistant.",
                            "template": "Summarize incident {{ trigger.payload.incident_id }}.",
                            "temperature": "0.2",
                            "max_tokens": "120",
                            "extra_body_json": "{\"response_format\": {\"type\": \"json_object\"}}",
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
        self._bind_secret(
            workflow=workflow,
            secret_name="OPENAI_COMPATIBLE_API_KEY",
        )

        def fake_urlopen(request, timeout=20):
            self.assertEqual(timeout, 20)
            self.assertEqual(request.full_url, "https://llm.example.com/v1/chat/completions")
            self.assertEqual(request.headers["Authorization"], "Bearer llm-secret")
            body = loads(request.data.decode("utf-8"))
            self.assertEqual(body["model"], "gpt-4.1-mini")
            self.assertEqual(body["messages"][0]["role"], "system")
            self.assertEqual(body["messages"][1]["content"], "Summarize incident INC-77.")
            self.assertEqual(body["temperature"], 0.2)
            self.assertEqual(body["max_tokens"], 120)
            self.assertEqual(body["response_format"]["type"], "json_object")
            return _FakeJsonResponse(
                {
                    "id": "chatcmpl-123",
                    "model": "gpt-4.1-mini",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "content": "{\"summary\":\"Investigate the failing deployment.\"}",
                            },
                        }
                    ],
                    "usage": {"prompt_tokens": 34, "completion_tokens": 12, "total_tokens": 46},
                }
            )

        with patch.dict(os.environ, {"OPENAI_COMPATIBLE_API_KEY": "llm-secret"}, clear=False):
            with patch("automation.tools.base.urlopen", side_effect=fake_urlopen):
                run = execute_workflow(workflow, input_data={"incident_id": "INC-77"})

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.step_results[1]["result"]["api_type"], "openai")
        self.assertEqual(run.step_results[1]["result"]["tool_name"], "openai_compatible_chat")
        self.assertNotIn("resource", run.step_results[1]["result"])
        self.assertNotIn("operation", run.step_results[1]["result"])
        self.assertEqual(run.output_data["response"]["text"], "{\"summary\":\"Investigate the failing deployment.\"}")
        self.assertEqual(run.context_data["llm"]["response"]["usage"]["total_tokens"], 46)
