from django.test import SimpleTestCase

from automation.primitives import WORKFLOW_NODE_TEMPLATE_MAP, normalize_workflow_definition_nodes


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
        self.assertEqual(mcp_template["config"]["auth_secret_group_id"], "")
        self.assertIn("auth_secret_group_id", fields_by_key)
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
        self.assertNotIn("resource", github_fields)
        self.assertNotIn("operation", github_fields)
        self.assertIn("signature_secret_name", github_fields)
        self.assertIn("auth_secret_group_id", github_fields)

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
        self.assertIn("bearer_token_name", prometheus_fields)

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
