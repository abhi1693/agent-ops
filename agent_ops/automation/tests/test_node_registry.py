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

    def test_internal_python_backed_node_registry_is_unified(self):
        self.assertEqual(
            [definition.type for definition in WORKFLOW_NODE_DEFINITIONS],
            [
                "core.manual_trigger",
                "core.schedule_trigger",
                "core.agent",
                "core.set",
                "core.if",
                "core.switch",
                "core.response",
                "core.stop_and_error",
                "utilities.action.template",
                "utilities.action.secret",
                "github.trigger.webhook",
                "alertmanager.trigger.webhook",
                "kibana.trigger.webhook",
                "prometheus.action.query",
                "elasticsearch.action.search",
                "openai.model.chat",
                "deepseek.model.chat",
                "fireworks.model.chat",
                "groq.model.chat",
                "mistral.model.chat",
                "openrouter.model.chat",
                "xai.model.chat",
                "infrastructure.action.kubectl",
                "mcp.action.tool",
            ],
        )

    def test_internal_node_registry_exposes_python_backed_templates(self):
        templates_by_type = {
            template["type"]: template
            for template in WORKFLOW_NODE_TEMPLATES
        }

        self.assertEqual(
            set(templates_by_type),
            {
                "core.manual_trigger",
                "core.schedule_trigger",
                "core.agent",
                "core.set",
                "core.if",
                "core.switch",
                "core.response",
                "core.stop_and_error",
                "utilities.action.template",
                "utilities.action.secret",
                "github.trigger.webhook",
                "alertmanager.trigger.webhook",
                "kibana.trigger.webhook",
                "openai.model.chat",
                "deepseek.model.chat",
                "fireworks.model.chat",
                "groq.model.chat",
                "mistral.model.chat",
                "openrouter.model.chat",
                "xai.model.chat",
                "prometheus.action.query",
                "elasticsearch.action.search",
                "infrastructure.action.kubectl",
                "mcp.action.tool",
            },
        )
        self.assertEqual(
            get_workflow_node_template(node_type="core.if")["type"],
            "core.if",
        )
        self.assertEqual(
            get_workflow_node_template(node_type="github.trigger.webhook")["type"],
            "github.trigger.webhook",
        )
        self.assertEqual(get_workflow_node_definition("core.agent").type, "core.agent")
        self.assertEqual(get_workflow_node_definition("core.response").type, "core.response")
        self.assertEqual(
            get_workflow_node_template(node_type="openai.model.chat")["type"],
            "openai.model.chat",
        )
        self.assertIsNone(get_workflow_node_definition("condition"))
        self.assertIsNone(get_workflow_node_template(node_type="tool.openai_compatible_chat"))

        set_template = templates_by_type["core.set"]
        self.assertEqual(set_template["label"], "Set")
        self.assertEqual(set_template["catalog_section"], "data")
        self.assertEqual(set_template["config"]["output_key"], "tool.output")
        self.assertEqual(set_template["fields"][0]["key"], "output_key")
        self.assertEqual(set_template["fields"][0]["ui_group"], "result")
        self.assertEqual(set_template["fields"][0]["binding"], "path")

        chat_model_template = templates_by_type["openai.model.chat"]
        self.assertEqual(chat_model_template["label"], "OpenAI")
        self.assertEqual(chat_model_template["catalog_section"], "apps")
        self.assertEqual(chat_model_template["config"]["custom_model"], "")
        self.assertEqual(chat_model_template["fields"][0]["key"], "base_url")
        self.assertEqual(chat_model_template["fields"][1]["type"], "select")
        self.assertEqual(chat_model_template["fields"][2]["key"], "custom_model")

        deepseek_template = templates_by_type["deepseek.model.chat"]
        self.assertEqual(deepseek_template["label"], "DeepSeek")
        self.assertEqual(deepseek_template["config"]["model"], "deepseek-chat")

        groq_template = templates_by_type["groq.model.chat"]
        self.assertEqual(groq_template["label"], "Groq")
        self.assertEqual(groq_template["config"]["base_url"], "https://api.groq.com/openai/v1")

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
                            "uiGroup": "input",
                            "binding": "template",
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

        self.assertEqual(serialized["catalog_section"], "data")
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
        self.assertEqual(serialized["fields"][1]["ui_group"], "input")
        self.assertEqual(serialized["fields"][1]["binding"], "template")

    def test_registry_validates_and_executes_manifest_trigger_and_tool_nodes(self):
        tool_node = {
            "id": "tool-1",
            "kind": "tool",
            "type": "utilities.action.template",
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
            "type": "github.trigger.webhook",
            "label": "GitHub",
            "config": {
                "secret_name": "GITHUB_WEBHOOK_SECRET",
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
            "utilities.action.template",
        )
        self.assertEqual(
            validate_workflow_node(
                node=trigger_node,
                outgoing_targets=["tool-1"],
                node_ids={"trigger-1", "tool-1"},
            ).type,
            "github.trigger.webhook",
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
            connected_nodes_by_port={},
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
            connected_nodes_by_port={},
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
        self.assertEqual(trigger_result.output["trigger_type"], "github.trigger.webhook")
        self.assertEqual(trigger_result.output["trigger_meta"], {"source": "github"})

    def test_registry_webhook_helper_uses_node_webhook_handler(self):
        request = self.request_factory.post("/webhook", data=b"{}", content_type="application/json")
        trigger_node = {
            "id": "trigger-1",
            "kind": "trigger",
            "type": "core.manual_trigger",
            "label": "Manual",
            "config": {},
        }

        with self.assertRaises(ValidationError):
            prepare_workflow_node_webhook_request(
                workflow=object(),
                node=trigger_node,
                request=request,
            )
