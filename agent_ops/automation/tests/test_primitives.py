from django.test import SimpleTestCase

from django.core.exceptions import ValidationError

from automation.primitives import (
    WORKFLOW_NODE_TEMPLATE_MAP,
    canonicalize_workflow_definition,
    normalize_workflow_definition_nodes,
    validate_workflow_runtime_definition,
)


class WorkflowPrimitiveNormalizationTests(SimpleTestCase):
    def test_catalog_template_map_contains_only_supported_catalog_node_ids(self):
        self.assertEqual(
            set(WORKFLOW_NODE_TEMPLATE_MAP.keys()),
            {
                "core.agent",
                "core.if",
                "core.manual_trigger",
                "core.response",
                "core.schedule_trigger",
                "core.set",
                "core.stop_and_error",
                "core.switch",
                "elasticsearch.action.search",
                "github.trigger.webhook",
                "openai.model.chat",
                "prometheus.action.query",
            },
        )

    def test_catalog_templates_expose_current_runtime_fields(self):
        agent_template = WORKFLOW_NODE_TEMPLATE_MAP["core.agent"]
        response_template = WORKFLOW_NODE_TEMPLATE_MAP["core.response"]
        github_template = WORKFLOW_NODE_TEMPLATE_MAP["github.trigger.webhook"]
        prometheus_template = WORKFLOW_NODE_TEMPLATE_MAP["prometheus.action.query"]
        elasticsearch_template = WORKFLOW_NODE_TEMPLATE_MAP["elasticsearch.action.search"]

        self.assertEqual(agent_template["catalog_section"], "flow")
        self.assertEqual(
            {field["key"] for field in agent_template["fields"]},
            {"template", "system_prompt", "output_key"},
        )
        self.assertEqual(response_template["catalog_section"], "flow")
        self.assertEqual(
            {field["key"] for field in response_template["fields"]},
            {"status", "template", "value_path"},
        )
        self.assertEqual(github_template["catalog_section"], "triggers")
        self.assertEqual(
            {field["key"] for field in github_template["fields"]},
            {"owner", "repository", "events"},
        )
        self.assertEqual(prometheus_template["config"]["output_key"], "prometheus.query")
        self.assertEqual(
            {field["key"] for field in prometheus_template["fields"]},
            {"query", "instant", "time", "output_key"},
        )
        self.assertEqual(elasticsearch_template["config"]["output_key"], "elasticsearch.search")
        self.assertEqual(
            {field["key"] for field in elasticsearch_template["fields"]},
            {"index", "query_json", "size", "auth_scheme", "output_key"},
        )

    def test_normalize_agent_node_applies_agent_defaults(self):
        definition = {
            "nodes": [
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
            ],
            "edges": [],
        }

        normalized = normalize_workflow_definition_nodes(definition)

        self.assertEqual(normalized["nodes"][0]["kind"], "agent")
        self.assertEqual(normalized["nodes"][0]["type"], "core.agent")
        self.assertEqual(normalized["nodes"][0]["config"]["template"], "hello")
        self.assertEqual(normalized["nodes"][0]["config"]["output_key"], "llm.response")

    def test_normalize_workflow_definition_prunes_invalid_input_mode_overrides(self):
        definition = {
            "nodes": [
                {
                    "id": "set-1",
                    "kind": "tool",
                    "type": "core.set",
                    "label": "Set",
                    "config": {
                        "value": "hello",
                        "__input_modes": {
                            "value": "expression",
                            "output_key": "expression",
                            "missing": "expression",
                            "invalid": "dynamic",
                        },
                    },
                    "position": {"x": 320, "y": 40},
                },
            ],
            "edges": [],
        }

        normalized = normalize_workflow_definition_nodes(definition)

        self.assertEqual(
            normalized["nodes"][0]["config"]["__input_modes"],
            {
                "value": "expression",
                "output_key": "expression",
            },
        )

    def test_canonicalize_workflow_definition_writes_v2_shape(self):
        definition = {
            "nodes": [
                {
                    "id": "agent-1",
                    "kind": "agent",
                    "label": "Planner",
                    "type": "core.agent",
                    "config": {
                        "template": "Plan {{ trigger.payload.ticket_id }}",
                        "output_key": "llm.response",
                    },
                    "position": {"x": 320, "y": 80},
                },
                {
                    "id": "model-1",
                    "kind": "tool",
                    "label": "OpenAI chat model",
                    "type": "openai.model.chat",
                    "config": {
                        "connection_id": "42",
                        "model": "gpt-4.1-mini",
                        "base_url": "https://api.openai.com/v1",
                    },
                    "position": {"x": 320, "y": 240},
                },
            ],
            "edges": [
                {
                    "id": "edge-1",
                    "source": "model-1",
                    "sourcePort": "ai_languageModel",
                    "target": "agent-1",
                    "targetPort": "ai_languageModel",
                },
            ],
        }

        canonical = canonicalize_workflow_definition(definition)

        self.assertEqual(canonical["definition_version"], 2)
        self.assertEqual(canonical["nodes"][0]["kind"], "agent")
        self.assertEqual(canonical["nodes"][0]["name"], "Planner")
        self.assertEqual(
            canonical["nodes"][0]["parameters"],
            {"template": "Plan {{ trigger.payload.ticket_id }}"},
        )
        self.assertEqual(canonical["nodes"][1]["kind"], "tool")
        self.assertEqual(canonical["nodes"][1]["connection_id"], "42")
        self.assertEqual(
            canonical["nodes"][1]["parameters"],
            {"model": "gpt-4.1-mini", "base_url": "https://api.openai.com/v1"},
        )
        self.assertEqual(canonical["edges"][0]["source_port"], "ai_languageModel")
        self.assertEqual(canonical["edges"][0]["target_port"], "ai_languageModel")

    def test_runtime_validation_allows_agent_auxiliary_model_and_tool_edges(self):
        definition = normalize_workflow_definition_nodes(
            {
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
                        "template": "Summarize {{ trigger.payload.ticket_id }}",
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
                        "base_url": "https://api.openai.com/v1",
                        "model": "gpt-4.1-mini",
                        "secret_name": "OPENAI_API_KEY",
                    },
                    "position": {"x": 320, "y": 240},
                },
                {
                    "id": "tool-1",
                    "kind": "tool",
                    "type": "core.set",
                    "label": "Set tool",
                    "config": {
                        "output_key": "template.result",
                        "value": "Weather summary for {{ trigger.payload.city }}",
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
                    "id": "model-1",
                    "kind": "tool",
                    "type": "openai.model.chat",
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
                    "type": "openai.model.chat",
                    "label": "OpenAI chat model B",
                    "config": {
                        "base_url": "https://api.openai.com/v1",
                        "model": "gpt-4.1-mini",
                        "secret_name": "OPENAI_API_KEY_2",
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
