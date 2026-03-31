from django.test import SimpleTestCase

from automation.triggers import WORKFLOW_TRIGGER_DEFINITIONS
from automation.triggers.base import (
    WorkflowTriggerFieldDefinition,
    trigger_text_field,
    trigger_textarea_field,
)


class WorkflowTriggerFieldDefinitionTests(SimpleTestCase):
    def test_trigger_field_serializes_to_designer_shape(self):
        field = trigger_text_field(
            "secret_header",
            "Secret header",
            placeholder="X-AgentOps-Webhook-Secret",
            help_text="Optional shared secret header name.",
        )

        self.assertEqual(
            field.serialize(),
            {
                "key": "secret_header",
                "label": "Secret header",
                "type": "text",
                "placeholder": "X-AgentOps-Webhook-Secret",
                "help_text": "Optional shared secret header name.",
            },
        )

    def test_trigger_field_definition_rejects_invalid_shape(self):
        with self.assertRaisesMessage(ValueError, 'Field "query" can only define rows for textarea fields.'):
            WorkflowTriggerFieldDefinition(
                key="query",
                label="Query",
                type="text",
                rows=4,
            )

    def test_trigger_registry_still_serializes_plain_json_field_payloads(self):
        github_trigger = next(
            trigger_definition
            for trigger_definition in WORKFLOW_TRIGGER_DEFINITIONS
            if trigger_definition["name"] == "github_webhook"
        )

        events_field = next(
            field
            for field in github_trigger["fields"]
            if field["key"] == "events"
        )

        self.assertEqual(
            events_field,
            trigger_text_field(
                "events",
                "Allowed events",
                placeholder="push,pull_request",
                help_text="Optional comma-separated allow-list. Leave blank to accept all GitHub events.",
            ).serialize(),
        )

    def test_trigger_textarea_helper_serializes_rows(self):
        self.assertEqual(
            trigger_textarea_field(
                "payload_template",
                "Payload template",
                rows=5,
                placeholder='{"message": "hello"}',
            ).serialize(),
            {
                "key": "payload_template",
                "label": "Payload template",
                "type": "textarea",
                "rows": 5,
                "placeholder": '{"message": "hello"}',
            },
        )
