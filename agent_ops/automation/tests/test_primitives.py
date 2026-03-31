from django.test import SimpleTestCase

from automation.primitives import WORKFLOW_NODE_TEMPLATE_MAP, normalize_workflow_definition_nodes


class WorkflowPrimitiveNormalizationTests(SimpleTestCase):
    def test_app_routed_templates_expose_resource_and_operation_metadata(self):
        llm_template = WORKFLOW_NODE_TEMPLATE_MAP["agent.openai"]
        github_template = WORKFLOW_NODE_TEMPLATE_MAP["trigger.github"]

        self.assertEqual(llm_template["resource"], "chat")
        self.assertEqual(llm_template["operation"], "complete")
        self.assertEqual(github_template["resource"], "webhook")
        self.assertEqual(github_template["operation"], "receive")

    def test_normalize_legacy_trigger_and_tool_nodes_to_concrete_types(self):
        definition = {
            "nodes": [
                {
                    "id": "trigger-1",
                    "kind": "trigger",
                    "label": "Manual",
                    "position": {"x": 32, "y": 40},
                },
                {
                    "id": "tool-1",
                    "kind": "tool",
                    "label": "Resolve key",
                    "config": {
                        "operation": "secret",
                        "name": "OPENAI_API_KEY",
                        "provider": "environment-variable",
                    },
                    "position": {"x": 320, "y": 40},
                },
            ],
            "edges": [],
        }

        normalized = normalize_workflow_definition_nodes(definition)

        self.assertEqual(normalized["nodes"][0]["type"], "trigger.manual")
        self.assertEqual(normalized["nodes"][0]["config"]["type"], "manual")
        self.assertEqual(normalized["nodes"][1]["type"], "tool.secret")
        self.assertEqual(normalized["nodes"][1]["config"]["tool_name"], "secret")
        self.assertEqual(normalized["nodes"][1]["config"]["operation"], "secret")
        self.assertEqual(normalized["nodes"][1]["config"]["output_key"], "credentials.value")

    def test_normalize_selector_based_agent_node_applies_template_defaults(self):
        definition = {
            "nodes": [
                {
                    "id": "agent-1",
                    "kind": "agent",
                    "type": "agent.openai",
                    "label": "OpenAI-compatible chat",
                    "config": {
                        "base_url": "https://llm.example.com/v1",
                        "api_key_name": "OPENAI_API_KEY",
                        "model": "gpt-4.1-mini",
                        "user_prompt": "hello",
                        "output_key": "llm.response",
                    },
                    "position": {"x": 320, "y": 40},
                },
            ],
            "edges": [],
        }

        normalized = normalize_workflow_definition_nodes(definition)

        self.assertEqual(normalized["nodes"][0]["kind"], "agent")
        self.assertEqual(normalized["nodes"][0]["type"], "agent.openai")
        self.assertEqual(normalized["nodes"][0]["config"]["resource"], "chat")
        self.assertEqual(normalized["nodes"][0]["config"]["operation"], "complete")
        self.assertNotIn("tool_name", normalized["nodes"][0]["config"])
        self.assertEqual(normalized["nodes"][0]["config"]["output_key"], "llm.response")
