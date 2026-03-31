from django.test import SimpleTestCase

from automation.primitives import WORKFLOW_NODE_TEMPLATE_MAP, normalize_workflow_definition_nodes


class WorkflowPrimitiveNormalizationTests(SimpleTestCase):
    def test_app_routed_templates_expose_resource_and_operation_metadata(self):
        github_template = WORKFLOW_NODE_TEMPLATE_MAP["trigger.github"]

        self.assertEqual(github_template["resource"], "webhook")
        self.assertEqual(github_template["operation"], "receive")

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
        self.assertEqual(mcp_template["config"]["tool_name"], "mcp_server")
        self.assertEqual(mcp_template["config"]["auth_secret_group_id"], "")
        self.assertIn("auth_secret_group_id", fields_by_key)
        self.assertEqual(fields_by_key["remote_tool_name"]["placeholder"], "weather_current")
        self.assertEqual(fields_by_key["timeout_seconds"]["placeholder"], "30")

    def test_manifest_backed_app_templates_own_runtime_fields(self):
        template_template = WORKFLOW_NODE_TEMPLATE_MAP["tool.template"]
        secret_template = WORKFLOW_NODE_TEMPLATE_MAP["tool.secret"]
        agent_template = WORKFLOW_NODE_TEMPLATE_MAP["agent"]
        response_template = WORKFLOW_NODE_TEMPLATE_MAP["response"]
        github_template = WORKFLOW_NODE_TEMPLATE_MAP["trigger.github"]

        template_fields = {field["key"] for field in template_template["fields"]}
        secret_fields = {field["key"] for field in secret_template["fields"]}
        agent_fields = {field["key"] for field in agent_template["fields"]}
        response_fields = {field["key"] for field in response_template["fields"]}
        github_fields = {field["key"] for field in github_template["fields"]}

        self.assertEqual(
            agent_fields,
            {
                "api_type",
                "output_key",
                "template",
                "auth_secret_group_id",
                "base_url",
                "api_key_name",
                "api_key_provider",
                "model",
                "system_prompt",
                "temperature",
                "max_tokens",
                "extra_body_json",
            },
        )
        self.assertEqual(template_fields, {"output_key", "template"})
        self.assertEqual(
            secret_fields,
            {"auth_secret_group_id", "output_key", "name", "provider"},
        )
        self.assertEqual(response_fields, {"status", "template", "value_path"})
        self.assertIn("signature_secret_name", github_fields)
        self.assertIn("auth_secret_group_id", github_fields)

    def test_observability_template_uses_manifest_field_rules(self):
        observability_template = WORKFLOW_NODE_TEMPLATE_MAP["tool.observability"]
        fields_by_key = {
            field["key"]: field
            for field in observability_template["fields"]
        }

        self.assertEqual(
            fields_by_key["operation"]["options_by_field"],
            {
                "resource": {
                    "prometheus": [{"value": "query", "label": "Query"}],
                    "elasticsearch": [{"value": "search", "label": "Search"}],
                }
            },
        )
        self.assertEqual(
            fields_by_key["query_json"]["visible_when"],
            {"resource": ["elasticsearch"]},
        )
        self.assertEqual(
            fields_by_key["bearer_token_name"]["visible_when"],
            {"resource": ["prometheus"]},
        )

    def test_legacy_tool_operation_nodes_no_longer_normalize_to_concrete_types(self):
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

        self.assertNotIn("type", normalized["nodes"][0])
        self.assertEqual(normalized["nodes"][0].get("config", {}), {})
        self.assertNotIn("type", normalized["nodes"][1])
        self.assertEqual(normalized["nodes"][1]["config"]["operation"], "secret")

    def test_legacy_core_wrapper_types_no_longer_normalize_to_builtin_node_types(self):
        definition = {
            "nodes": [
                {
                    "id": "trigger-1",
                    "kind": "trigger",
                    "type": "trigger.manual",
                    "label": "Manual",
                    "position": {"x": 32, "y": 40},
                },
                {
                    "id": "tool-1",
                    "kind": "tool",
                    "type": "tool.set",
                    "label": "Set",
                    "config": {
                        "tool_name": "set",
                        "output_key": "context.value",
                        "value": "hello",
                    },
                    "position": {"x": 320, "y": 40},
                },
                {
                    "id": "condition-1",
                    "kind": "condition",
                    "type": "condition",
                    "label": "If",
                    "config": {
                        "path": "context.value",
                        "operator": "equals",
                        "right_value": "hello",
                        "true_target": "done-1",
                        "false_target": "done-2",
                    },
                    "position": {"x": 608, "y": 40},
                },
            ],
            "edges": [],
        }

        normalized = normalize_workflow_definition_nodes(definition)

        self.assertEqual(normalized["nodes"][0]["type"], "trigger.manual")
        self.assertEqual(normalized["nodes"][1]["type"], "tool.set")
        self.assertEqual(normalized["nodes"][2]["type"], "condition")

    def test_normalize_agent_node_applies_openai_defaults(self):
        definition = {
            "nodes": [
                {
                    "id": "agent-1",
                    "kind": "agent",
                    "type": "agent",
                    "label": "OpenAI chat",
                    "config": {
                        "base_url": "https://llm.example.com/v1",
                        "api_key_name": "OPENAI_API_KEY",
                        "model": "gpt-4.1-mini",
                        "template": "hello",
                        "output_key": "llm.response",
                    },
                    "position": {"x": 320, "y": 40},
                },
            ],
            "edges": [],
        }

        normalized = normalize_workflow_definition_nodes(definition)

        self.assertEqual(normalized["nodes"][0]["kind"], "agent")
        self.assertEqual(normalized["nodes"][0]["type"], "agent")
        self.assertEqual(normalized["nodes"][0]["config"]["api_type"], "openai")
        self.assertEqual(normalized["nodes"][0]["config"]["template"], "hello")
        self.assertEqual(normalized["nodes"][0]["config"]["output_key"], "llm.response")
