from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from automation.tools import WORKFLOW_TOOL_DEFINITIONS, validate_workflow_tool_config
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

    def test_tool_registry_still_serializes_plain_json_field_payloads(self):
        elasticsearch_tool = next(
            tool_definition
            for tool_definition in WORKFLOW_TOOL_DEFINITIONS
            if tool_definition["name"] == "elasticsearch_search"
        )

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

    def test_mcp_server_tool_definition_serializes_expected_fields(self):
        mcp_tool = next(
            tool_definition
            for tool_definition in WORKFLOW_TOOL_DEFINITIONS
            if tool_definition["name"] == "mcp_server"
        )

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

    def test_tool_config_rejects_legacy_operation_alias(self):
        with self.assertRaises(ValidationError) as exc_info:
            validate_workflow_tool_config(
                {
                    "operation": "secret",
                    "name": "OPENAI_API_KEY",
                },
                node_id="tool-1",
            )

        self.assertEqual(
            exc_info.exception.message_dict,
            {"definition": ['Node "tool-1" must define config.tool_name.']},
        )
