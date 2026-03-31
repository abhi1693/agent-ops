from django.core.exceptions import ValidationError
from django.template import Context, Engine
from django.test import RequestFactory
from django.test import SimpleTestCase

from automation.nodes import (
    WORKFLOW_NODE_DEFINITIONS,
    WORKFLOW_NODE_TEMPLATES,
    execute_workflow_node,
    get_workflow_node_definition,
    get_workflow_node_template,
    prepare_workflow_node_webhook_request,
    validate_workflow_node,
)
from automation.nodes.base import WorkflowNodeDefinition


class WorkflowNodeRegistryTests(SimpleTestCase):
    def setUp(self):
        self.request_factory = RequestFactory()

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

    def test_registry_validates_and_executes_manifest_trigger_and_tool_nodes(self):
        tool_node = {
            "id": "tool-1",
            "kind": "tool",
            "type": "tool.template",
            "label": "Render template",
            "config": {
                "tool_name": "template",
                "output_key": "draft",
                "template": "Hello {{ trigger.payload.name }}",
            },
        }
        trigger_node = {
            "id": "trigger-1",
            "kind": "trigger",
            "type": "trigger.github_webhook",
            "label": "GitHub",
            "config": {
                "type": "github_webhook",
                "signature_secret_name": "GITHUB_WEBHOOK_SECRET",
            },
        }
        context = {
            "trigger": {
                "payload": {"name": "Ada"},
                "meta": {"source": "github"},
            }
        }

        self.assertEqual(
            validate_workflow_node(node=tool_node, outgoing_targets=["done"], node_ids={"tool-1", "done"}).type,
            "tool.template",
        )
        self.assertEqual(
            validate_workflow_node(
                node=trigger_node,
                outgoing_targets=["tool-1"],
                node_ids={"trigger-1", "tool-1"},
            ).type,
            "trigger.github_webhook",
        )

        template_engine = Engine(debug=False)

        def render_template(template: str, runtime_context: dict) -> str:
            return template_engine.from_string(template).render(Context(runtime_context)).strip()

        def set_path_value(data: dict, path: str, value):
            data[path] = value

        tool_result = execute_workflow_node(
            workflow=None,
            node=tool_node,
            next_node_id="done",
            context=context,
            secret_paths=set(),
            secret_values=[],
            render_template=render_template,
            get_path_value=lambda data, path: data if not path else data.get(path),
            set_path_value=set_path_value,
            resolve_scoped_secret=lambda **kwargs: None,
            evaluate_condition=lambda operator, left, right: left == right,
        )
        trigger_result = execute_workflow_node(
            workflow=None,
            node=trigger_node,
            next_node_id="tool-1",
            context=context,
            secret_paths=set(),
            secret_values=[],
            render_template=render_template,
            get_path_value=lambda data, path: data if not path else data.get(path),
            set_path_value=set_path_value,
            resolve_scoped_secret=lambda **kwargs: None,
            evaluate_condition=lambda operator, left, right: left == right,
        )

        self.assertEqual(tool_result.output["tool_name"], "template")
        self.assertEqual(tool_result.output["value"], "Hello Ada")
        self.assertEqual(context["draft"], "Hello Ada")
        self.assertEqual(trigger_result.output["payload"], {"name": "Ada"})
        self.assertEqual(trigger_result.output["trigger_type"], "github_webhook")
        self.assertEqual(trigger_result.output["trigger_meta"], {"source": "github"})

    def test_registry_webhook_helper_delegates_to_trigger_registry(self):
        request = self.request_factory.post("/webhook", data=b"{}", content_type="application/json")
        trigger_node = {
            "id": "trigger-1",
            "kind": "trigger",
            "type": "n8n-nodes-base.manualTrigger",
            "label": "Manual",
            "config": {},
        }

        with self.assertRaises(ValidationError):
            prepare_workflow_node_webhook_request(
                workflow=object(),
                node=trigger_node,
                request=request,
            )
