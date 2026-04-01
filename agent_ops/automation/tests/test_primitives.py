from django.test import SimpleTestCase

from django.core.exceptions import ValidationError

from automation.primitives import (
    WORKFLOW_NODE_TEMPLATE_MAP,
    normalize_workflow_definition_nodes,
    validate_workflow_runtime_definition,
)


class WorkflowPrimitiveNormalizationTests(SimpleTestCase):
    def test_app_routed_templates_do_not_expose_route_metadata(self):
        github_template = WORKFLOW_NODE_TEMPLATE_MAP["trigger.github_webhook"]

        self.assertNotIn("resource", github_template)
        self.assertNotIn("operation", github_template)

    def test_manifest_backed_app_templates_preserve_manifest_defaults(self):
        mcp_template = WORKFLOW_NODE_TEMPLATE_MAP["tool.mcp_server"]
        fields_by_key = {
            field["key"]: field
            for field in mcp_template["fields"]
        }

        self.assertEqual(mcp_template["app_id"], "integrations")
        self.assertEqual(mcp_template["label"], "MCP server")
        self.assertEqual(mcp_template["config"]["protocol_version"], "2025-11-25")
        self.assertEqual(mcp_template["config"]["timeout_seconds"], 30)
        self.assertNotIn("tool_name", mcp_template["config"])
        self.assertNotIn("auth_secret_group_id", mcp_template["config"])
        self.assertNotIn("auth_secret_group_id", fields_by_key)
        self.assertEqual(fields_by_key["remote_tool_name"]["placeholder"], "weather_current")
        self.assertEqual(fields_by_key["timeout_seconds"]["placeholder"], "30")

    def test_manifest_backed_app_templates_own_runtime_fields(self):
        template_template = WORKFLOW_NODE_TEMPLATE_MAP["tool.template"]
        secret_template = WORKFLOW_NODE_TEMPLATE_MAP["tool.secret"]
        agent_template = WORKFLOW_NODE_TEMPLATE_MAP["agent"]
        response_template = WORKFLOW_NODE_TEMPLATE_MAP["response"]
        github_template = WORKFLOW_NODE_TEMPLATE_MAP["trigger.github_webhook"]

        template_fields = {field["key"] for field in template_template["fields"]}
        secret_fields = {field["key"] for field in secret_template["fields"]}
        agent_fields = {field["key"] for field in agent_template["fields"]}
        response_fields = {field["key"] for field in response_template["fields"]}
        github_fields = {field["key"] for field in github_template["fields"]}

        self.assertEqual(
            agent_fields,
            {
                "output_key",
                "template",
                "system_prompt",
            },
        )
        self.assertEqual(template_fields, {"output_key", "template"})
        self.assertEqual(
            secret_fields,
            {"output_key", "secret_name", "secret_group_id"},
        )
        self.assertEqual(response_fields, {"status", "template", "value_path"})
        self.assertNotIn("resource", github_fields)
        self.assertNotIn("operation", github_fields)
        self.assertEqual(github_fields, {"events", "secret_name", "secret_group_id"})

    def test_concrete_observability_templates_are_route_specific(self):
        prometheus_template = WORKFLOW_NODE_TEMPLATE_MAP["tool.prometheus_query"]
        elasticsearch_template = WORKFLOW_NODE_TEMPLATE_MAP["tool.elasticsearch_search"]
        alertmanager_template = WORKFLOW_NODE_TEMPLATE_MAP["trigger.alertmanager_webhook"]

        prometheus_fields = {field["key"] for field in prometheus_template["fields"]}
        elasticsearch_fields = {field["key"] for field in elasticsearch_template["fields"]}
        alertmanager_fields = {field["key"] for field in alertmanager_template["fields"]}

        self.assertEqual(prometheus_template["config"]["output_key"], "prometheus.query")
        self.assertNotIn("resource", prometheus_template)
        self.assertNotIn("operation", prometheus_template)
        self.assertNotIn("resource", prometheus_fields)
        self.assertNotIn("operation", prometheus_fields)
        self.assertIn("query", prometheus_fields)
        self.assertNotIn("bearer_token_name", prometheus_fields)

        self.assertEqual(elasticsearch_template["config"]["output_key"], "elasticsearch.search")
        self.assertNotIn("resource", elasticsearch_template)
        self.assertNotIn("operation", elasticsearch_template)
        self.assertNotIn("resource", elasticsearch_fields)
        self.assertNotIn("operation", elasticsearch_fields)
        self.assertIn("query_json", elasticsearch_fields)
        self.assertIn("auth_scheme", elasticsearch_fields)

        self.assertNotIn("resource", alertmanager_template)
        self.assertNotIn("operation", alertmanager_template)
        self.assertNotIn("resource", alertmanager_fields)
        self.assertNotIn("operation", alertmanager_fields)

    def test_normalize_agent_node_applies_agent_defaults(self):
        definition = {
            "nodes": [
                {
                    "id": "agent-1",
                    "kind": "agent",
                    "type": "agent",
                    "label": "AI Agent",
                    "config": {
                        "template": "hello",
                    },
                    "position": {"x": 320, "y": 40},
                },
            ],
            "edges": [],
        }

        normalized = normalize_workflow_definition_nodes(definition)

        self.assertEqual(normalized["nodes"][0]["kind"], "agent")
        self.assertEqual(normalized["nodes"][0]["type"], "agent")
        self.assertEqual(normalized["nodes"][0]["config"]["template"], "hello")
        self.assertEqual(normalized["nodes"][0]["config"]["output_key"], "llm.response")

    def test_normalize_manifest_trigger_and_tool_nodes_injects_runtime_identifiers(self):
        definition = {
            "nodes": [
                {
                    "id": "trigger-1",
                    "kind": "trigger",
                    "type": "trigger.github_webhook",
                    "label": "GitHub webhook",
                    "config": {},
                },
                {
                    "id": "tool-1",
                    "kind": "tool",
                    "type": "tool.prometheus_query",
                    "label": "Prometheus query",
                    "config": {
                        "base_url": "https://prometheus.example.com",
                        "query": "up",
                    },
                },
            ],
            "edges": [],
        }

        normalized = normalize_workflow_definition_nodes(definition)

        self.assertEqual(normalized["nodes"][0]["config"]["type"], "github_webhook")
        self.assertEqual(normalized["nodes"][1]["config"]["tool_name"], "prometheus_query")
        self.assertEqual(
            normalized["nodes"][1]["config"]["output_key"],
            "prometheus.query",
        )

    def test_runtime_validation_allows_agent_auxiliary_model_and_tool_edges(self):
        definition = normalize_workflow_definition_nodes(
            {
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
                            "template": "Summarize {{ trigger.payload.ticket_id }}",
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
                    {
                        "id": "model-1",
                        "kind": "tool",
                        "type": "tool.deepseek_chat_model",
                        "label": "DeepSeek chat model",
                        "config": {
                            "base_url": "https://api.deepseek.com/v1",
                            "model": "deepseek-chat",
                            "secret_name": "DEEPSEEK_API_KEY",
                        },
                        "position": {"x": 320, "y": 240},
                    },
                    {
                        "id": "tool-1",
                        "kind": "tool",
                        "type": "tool.template",
                        "label": "Template tool",
                        "config": {
                            "output_key": "template.result",
                            "template": "Weather summary for {{ trigger.payload.city }}",
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
            }
        )

        validate_workflow_runtime_definition(
            nodes=definition["nodes"],
            edges=definition["edges"],
        )

    def test_runtime_validation_rejects_multiple_agent_chat_models(self):
        definition = normalize_workflow_definition_nodes(
            {
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
                            "template": "hello",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "model-1",
                        "kind": "tool",
                        "type": "tool.openai_chat_model",
                        "label": "OpenAI chat model A",
                        "config": {
                            "base_url": "https://api.openai.com/v1",
                            "model": "gpt-4.1-mini",
                            "secret_name": "OPENAI_API_KEY",
                        },
                        "position": {"x": 320, "y": 240},
                    },
                    {
                        "id": "model-2",
                        "kind": "tool",
                        "type": "tool.groq_chat_model",
                        "label": "Groq chat model",
                        "config": {
                            "base_url": "https://api.groq.com/openai/v1",
                            "model": "llama-3.3-70b-versatile",
                            "secret_name": "GROQ_API_KEY",
                        },
                        "position": {"x": 480, "y": 240},
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
                    {
                        "id": "edge-3",
                        "source": "model-2",
                        "sourcePort": "ai_languageModel",
                        "target": "agent-1",
                        "targetPort": "ai_languageModel",
                    },
                ],
            }
        )

        with self.assertRaises(ValidationError) as exc_info:
            validate_workflow_runtime_definition(
                nodes=definition["nodes"],
                edges=definition["edges"],
            )

        self.assertIn('accepts at most 1 connection(s) on port "ai_languageModel"', str(exc_info.exception))

    def test_runtime_validation_rejects_agent_without_connected_chat_model(self):
        definition = normalize_workflow_definition_nodes(
            {
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
                            "template": "hello",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "agent-1"},
                ],
            }
        )

        with self.assertRaises(ValidationError) as exc_info:
            validate_workflow_runtime_definition(
                nodes=definition["nodes"],
                edges=definition["edges"],
            )

        self.assertIn('must connect exactly one chat model on port "ai_languageModel"', str(exc_info.exception))
