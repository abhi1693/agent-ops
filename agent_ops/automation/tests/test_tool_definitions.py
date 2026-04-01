from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from automation.nodes import get_workflow_node_template, validate_workflow_node
from automation.tools.base import (
    WorkflowToolFieldDefinition,
    tool_field_option,
    tool_select_field,
    tool_textarea_field,
)


class WorkflowToolFieldDefinitionTests(SimpleTestCase):
    def test_select_field_serializes_to_designer_shape(self):
        field = tool_select_field(
            "auth_scheme",
            "Auth scheme",
            options=(
                tool_field_option("ApiKey"),
                tool_field_option("Bearer"),
            ),
        )

        self.assertEqual(
            field.serialize(),
            {
                "key": "auth_scheme",
                "label": "Auth scheme",
                "type": "select",
                "options": [
                    {"value": "ApiKey", "label": "ApiKey"},
                    {"value": "Bearer", "label": "Bearer"},
                ],
            },
        )

    def test_tool_field_definition_rejects_invalid_shape(self):
        with self.assertRaisesMessage(ValueError, 'Field "query" can only define options for select fields.'):
            WorkflowToolFieldDefinition(
                key="query",
                label="Query",
                type="text",
                options=(tool_field_option("value"),),
            )

        with self.assertRaisesMessage(ValueError, 'Field "query" can only define rows for textarea fields.'):
            WorkflowToolFieldDefinition(
                key="query",
                label="Query",
                type="text",
                rows=4,
            )

    def test_tool_node_template_still_serializes_plain_json_field_payloads(self):
        elasticsearch_tool = get_workflow_node_template(node_type="tool.elasticsearch_search")

        auth_scheme_field = next(
            field
            for field in elasticsearch_tool["fields"]
            if field["key"] == "auth_scheme"
        )
        query_json_field = next(
            field
            for field in elasticsearch_tool["fields"]
            if field["key"] == "query_json"
        )

        self.assertEqual(auth_scheme_field["type"], "select")
        self.assertEqual(
            auth_scheme_field["options"],
            [
                {"value": "ApiKey", "label": "ApiKey"},
                {"value": "Bearer", "label": "Bearer"},
            ],
        )
        self.assertEqual(query_json_field, tool_textarea_field(
            "query_json",
            "Query JSON",
            rows=8,
            placeholder='{"size": 10, "query": {"match": {"service": "api"}}}',
        ).serialize())

    def test_mcp_server_tool_node_template_serializes_expected_fields(self):
        mcp_tool = get_workflow_node_template(node_type="tool.mcp_server")

        remote_tool_name_field = next(
            field
            for field in mcp_tool["fields"]
            if field["key"] == "remote_tool_name"
        )
        headers_json_field = next(
            field
            for field in mcp_tool["fields"]
            if field["key"] == "headers_json"
        )

        self.assertEqual(remote_tool_name_field["label"], "Server tool name")
        self.assertEqual(
            headers_json_field,
            tool_textarea_field(
                "headers_json",
                "Extra headers JSON",
                rows=5,
                placeholder='{"X-Tenant": "ops"}',
                help_text="Optional non-secret headers merged into every request. Auth and session headers are managed separately from stored Secret objects.",
            ).serialize(),
        )

    def test_chat_model_tool_templates_serialize_expected_fields(self):
        chat_model_tool = get_workflow_node_template(node_type="tool.openai_chat_model")
        deepseek_chat_model_tool = get_workflow_node_template(node_type="tool.deepseek_chat_model")
        groq_chat_model_tool = get_workflow_node_template(node_type="tool.groq_chat_model")

        self.assertEqual(chat_model_tool["label"], "OpenAI chat model")
        self.assertEqual(chat_model_tool["config"]["api_key_name"], "OPENAI_API_KEY")
        self.assertEqual(chat_model_tool["fields"][0]["key"], "auth_secret_group_id")
        self.assertEqual(chat_model_tool["fields"][1]["key"], "base_url")
        self.assertEqual(deepseek_chat_model_tool["label"], "DeepSeek chat model")
        self.assertEqual(deepseek_chat_model_tool["config"]["api_key_name"], "DEEPSEEK_API_KEY")
        self.assertEqual(deepseek_chat_model_tool["config"]["base_url"], "https://api.deepseek.com/v1")
        self.assertEqual(deepseek_chat_model_tool["fields"][1]["key"], "base_url")
        self.assertEqual(groq_chat_model_tool["label"], "Groq chat model")
        self.assertEqual(groq_chat_model_tool["config"]["model"], "llama-3.3-70b-versatile")

    def test_tool_node_validation_requires_base_url(self):
        with self.assertRaises(ValidationError) as exc_info:
            validate_workflow_node(
                node={
                    "id": "tool-1",
                    "kind": "tool",
                    "type": "tool.openai_chat_model",
                    "config": {
                        "api_key_name": "OPENAI_API_KEY",
                        "model": "gpt-4.1-mini",
                    },
                },
                outgoing_targets=["done"],
                node_ids={"tool-1", "done"},
            )

        self.assertEqual(
            exc_info.exception.message_dict,
            {"definition": ['Node "tool-1" must define config.base_url.']},
        )
