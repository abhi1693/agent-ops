from django.test import SimpleTestCase

from automation.nodes import (
    WORKFLOW_NODE_DEFINITIONS,
    WORKFLOW_NODE_TEMPLATES,
    get_workflow_node_definition,
    get_workflow_node_template,
)
from automation.nodes.base import WorkflowNodeDefinition


class WorkflowNodeRegistryTests(SimpleTestCase):
    def test_manifest_backed_node_registry_is_unified(self):
        self.assertEqual(
            [definition.type for definition in WORKFLOW_NODE_DEFINITIONS],
            [
                "n8n-nodes-base.manualTrigger",
                "n8n-nodes-base.scheduleTrigger",
                "agent",
                "n8n-nodes-base.set",
                "n8n-nodes-base.if",
                "n8n-nodes-base.switch",
                "response",
                "n8n-nodes-base.stopAndError",
                "tool.template",
                "tool.secret",
                "trigger.github_webhook",
                "trigger.alertmanager_webhook",
                "trigger.kibana_webhook",
                "tool.prometheus_query",
                "tool.elasticsearch_search",
                "tool.kubectl",
                "tool.mcp_server",
            ],
        )

    def test_node_registry_exposes_manifest_backed_templates(self):
        templates_by_type = {
            template["type"]: template
            for template in WORKFLOW_NODE_TEMPLATES
        }

        self.assertEqual(
            set(templates_by_type),
            {
                "n8n-nodes-base.manualTrigger",
                "n8n-nodes-base.scheduleTrigger",
                "agent",
                "n8n-nodes-base.set",
                "n8n-nodes-base.if",
                "n8n-nodes-base.switch",
                "response",
                "n8n-nodes-base.stopAndError",
                "tool.template",
                "tool.secret",
                "trigger.github_webhook",
                "trigger.alertmanager_webhook",
                "trigger.kibana_webhook",
                "tool.prometheus_query",
                "tool.elasticsearch_search",
                "tool.kubectl",
                "tool.mcp_server",
            },
        )
        self.assertEqual(
            get_workflow_node_template(node_type="n8n-nodes-base.if")["type"],
            "n8n-nodes-base.if",
        )
        self.assertEqual(
            get_workflow_node_template(node_type="trigger.github_webhook")["type"],
            "trigger.github_webhook",
        )
        self.assertEqual(get_workflow_node_definition("agent").type, "agent")
        self.assertEqual(get_workflow_node_definition("response").type, "response")
        self.assertIsNone(get_workflow_node_definition("condition"))

        set_template = templates_by_type["n8n-nodes-base.set"]
        self.assertEqual(set_template["label"], "Set")
        self.assertEqual(set_template["node_version"], "1.0.0")
        self.assertEqual(set_template["categories"], ["Core Nodes"])
        self.assertEqual(
            set_template["documentation_url"],
            "https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.set/",
        )
        self.assertEqual(set_template["config"]["output_key"], "tool.output")
        self.assertEqual(set_template["fields"][0]["key"], "output_key")

    def test_manifest_field_schema_supports_visibility_and_dynamic_options(self):
        definition = WorkflowNodeDefinition.from_manifest(
            {
                "node": "tool.testVisibility",
                "details": "Test node",
                "agentOps": {
                    "kind": "tool",
                    "displayName": "Test visibility",
                    "description": "Test visibility",
                    "icon": "mdi-flask-outline",
                    "fields": [
                        {
                            "key": "resource",
                            "label": "Resource",
                            "type": "select",
                            "options": [
                                {"value": "prometheus", "label": "Prometheus"},
                                {"value": "elasticsearch", "label": "Elasticsearch"},
                            ],
                        },
                        {
                            "key": "operation",
                            "label": "Operation",
                            "type": "select",
                            "visible_when": {
                                "resource": ["prometheus", "elasticsearch"],
                            },
                            "options_by_field": {
                                "resource": {
                                    "prometheus": [
                                        {"value": "query", "label": "Query"},
                                    ],
                                    "elasticsearch": [
                                        {"value": "search", "label": "Search"},
                                    ],
                                },
                            },
                        },
                    ],
                },
            }
        )

        serialized = definition.serialize()

        self.assertEqual(
            serialized["fields"][1]["visible_when"],
            {"resource": ["prometheus", "elasticsearch"]},
        )
        self.assertEqual(
            serialized["fields"][1]["options_by_field"],
            {
                "resource": {
                    "prometheus": [{"value": "query", "label": "Query"}],
                    "elasticsearch": [{"value": "search", "label": "Search"}],
                }
            },
        )
