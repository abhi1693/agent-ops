from django.test import SimpleTestCase

from automation.app_nodes import (
    WORKFLOW_APP_NODE_DEFINITIONS,
    WORKFLOW_APP_NODE_PACKAGE,
)
from automation.nodes import (
    WORKFLOW_BUILTIN_NODE_DEFINITIONS,
    WORKFLOW_BUILTIN_NODE_TEMPLATES,
    get_workflow_builtin_node_definition,
    get_workflow_builtin_node_template,
)
from automation.nodes.base import WorkflowNodeDefinition
from automation.nodes.registry import WORKFLOW_BUILTIN_NODE_PACKAGE


class WorkflowBuiltinNodeRegistryTests(SimpleTestCase):
    def test_builtin_node_registry_is_manifest_driven(self):
        self.assertEqual(WORKFLOW_BUILTIN_NODE_PACKAGE["name"], "agent-ops-builtins")
        self.assertEqual(WORKFLOW_BUILTIN_NODE_PACKAGE["version"], "0.1.0")
        self.assertEqual(
            WORKFLOW_BUILTIN_NODE_PACKAGE["agentOps"]["nodes"],
            [
                "core.manual_trigger.node",
                "core.schedule_trigger.node",
                "core.set.node",
                "core.if.node",
                "core.switch.node",
                "core.stop_and_error.node",
            ],
        )
        self.assertEqual(
            [definition.type for definition in WORKFLOW_BUILTIN_NODE_DEFINITIONS],
            [
                "n8n-nodes-base.manualTrigger",
                "n8n-nodes-base.scheduleTrigger",
                "n8n-nodes-base.set",
                "n8n-nodes-base.if",
                "n8n-nodes-base.switch",
                "n8n-nodes-base.stopAndError",
            ],
        )

    def test_builtin_node_registry_exposes_n8n_style_starter_nodes(self):
        templates_by_type = {
            template["type"]: template
            for template in WORKFLOW_BUILTIN_NODE_TEMPLATES
        }

        self.assertEqual(
            set(templates_by_type),
            {
                "n8n-nodes-base.manualTrigger",
                "n8n-nodes-base.scheduleTrigger",
                "n8n-nodes-base.set",
                "n8n-nodes-base.if",
                "n8n-nodes-base.switch",
                "n8n-nodes-base.stopAndError",
            },
        )
        self.assertEqual(
            get_workflow_builtin_node_template(node_type="n8n-nodes-base.if")["type"],
            "n8n-nodes-base.if",
        )
        self.assertIsNone(get_workflow_builtin_node_definition("trigger.manual"))
        self.assertIsNone(get_workflow_builtin_node_definition("tool.set"))
        self.assertIsNone(get_workflow_builtin_node_definition("condition"))

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


class WorkflowAppNodeRegistryTests(SimpleTestCase):
    def test_app_node_registry_is_manifest_driven(self):
        self.assertEqual(WORKFLOW_APP_NODE_PACKAGE["name"], "agent-ops-app-nodes")
        self.assertEqual(WORKFLOW_APP_NODE_PACKAGE["version"], "0.1.0")
        self.assertEqual(
            WORKFLOW_APP_NODE_PACKAGE["agentOps"]["nodes"],
            [
                "utilities.template",
                "utilities.secret",
                "github.webhook",
                "observability.alertmanager_webhook",
                "observability.kibana_webhook",
                "observability.prometheus_query",
                "observability.elasticsearch_search",
                "infrastructure.kubectl",
                "integrations.mcp_server",
            ],
        )
        self.assertEqual(
            [definition.template_definition.type for definition in WORKFLOW_APP_NODE_DEFINITIONS],
            [
                "tool.template",
                "tool.secret",
                "trigger.github",
                "trigger.alertmanager_webhook",
                "trigger.kibana_webhook",
                "tool.prometheus_query",
                "tool.elasticsearch_search",
                "tool.kubectl",
                "tool.mcp_server",
            ],
        )

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
