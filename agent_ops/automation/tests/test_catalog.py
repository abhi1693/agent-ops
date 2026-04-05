from django.test import SimpleTestCase

from automation.catalog.capabilities import (
    CAPABILITY_AGENT_MODEL,
    CAPABILITY_AGENT_TOOL,
    CAPABILITY_TRIGGER_MANUAL,
    CAPABILITY_TRIGGER_SCHEDULE,
    CAPABILITY_TRIGGER_WEBHOOK,
)
from automation.catalog.discovery import discover_integration_module_names
from automation.catalog.loader import build_workflow_catalog, initialize_workflow_catalog, reset_workflow_catalog
from automation.catalog.payloads import build_workflow_catalog_payload


class WorkflowCatalogTests(SimpleTestCase):
    def tearDown(self) -> None:
        reset_workflow_catalog()

    def test_discovers_native_integration_packages(self):
        self.assertEqual(
            discover_integration_module_names(),
            ("elasticsearch", "github", "openai", "prometheus"),
        )

    def test_build_workflow_catalog_registers_native_core_nodes_and_apps(self):
        registry = build_workflow_catalog()

        self.assertEqual(
            sorted(registry["core_nodes"]),
            [
                "core.agent",
                "core.if",
                "core.manual_trigger",
                "core.response",
                "core.schedule_trigger",
                "core.set",
                "core.stop_and_error",
                "core.switch",
                "core.webhook_trigger",
            ],
        )
        self.assertEqual(
            sorted(registry["integration_apps"]),
            ["elasticsearch", "github", "openai", "prometheus"],
        )
        self.assertIn("github.trigger.webhook", registry["node_types"])
        self.assertIn("prometheus.action.query", registry["node_types"])
        self.assertIn("elasticsearch.action.search", registry["node_types"])
        self.assertIn("openai.model.chat", registry["node_types"])

    def test_capability_index_is_populated_from_native_node_definitions(self):
        registry = build_workflow_catalog()

        self.assertEqual(registry["capability_index"][CAPABILITY_TRIGGER_MANUAL], {"core.manual_trigger"})
        self.assertEqual(registry["capability_index"][CAPABILITY_TRIGGER_SCHEDULE], {"core.schedule_trigger"})
        self.assertEqual(
            registry["capability_index"][CAPABILITY_TRIGGER_WEBHOOK],
            {"core.webhook_trigger", "github.trigger.webhook"},
        )
        self.assertEqual(
            registry["capability_index"][CAPABILITY_AGENT_TOOL],
            {"elasticsearch.action.search", "prometheus.action.query"},
        )
        self.assertEqual(registry["capability_index"][CAPABILITY_AGENT_MODEL], {"openai.model.chat"})

    def test_initialize_workflow_catalog_returns_cached_registry(self):
        first_registry = initialize_workflow_catalog()
        second_registry = initialize_workflow_catalog()

        self.assertIs(first_registry, second_registry)

    def test_native_catalog_node_definitions_do_not_expose_deprecated_metadata(self):
        registry = build_workflow_catalog()
        node_definition = registry["node_types"]["openai.model.chat"]
        serialized = node_definition.serialize()

        self.assertFalse(hasattr(node_definition, "legacy_node_type"))
        self.assertNotIn("legacy_node_type", serialized)
        self.assertEqual(serialized["parameter_schema"][0]["key"], "model")
        self.assertEqual(serialized["connection_slots"][0]["key"], "connection_id")
        self.assertEqual(serialized["connection_slots"][0]["allowed_connection_types"], ["openai.api"])
        self.assertEqual(serialized["type_version"], 1)

    def test_catalog_nodes_expose_explicit_connection_slots(self):
        registry = build_workflow_catalog()

        openai_node = registry["node_types"]["openai.model.chat"]
        self.assertEqual(openai_node.connection_slots[0].key, "connection_id")
        self.assertFalse(openai_node.connection_slots[0].required)
        self.assertEqual(openai_node.connection_slots[0].allowed_connection_types, ("openai.api",))

        prometheus_node = registry["node_types"]["prometheus.action.query"]
        self.assertTrue(prometheus_node.connection_slots[0].required)
        self.assertEqual(prometheus_node.connection_slots[0].allowed_connection_types, ("prometheus.api",))

        github_node = registry["node_types"]["github.trigger.webhook"]
        self.assertTrue(github_node.connection_slots[0].required)
        self.assertEqual(github_node.connection_slots[0].allowed_connection_types, ("github.oauth2",))

    def test_control_nodes_expose_named_output_ports(self):
        registry = build_workflow_catalog()

        if_node = registry["node_types"]["core.if"]
        switch_node = registry["node_types"]["core.switch"]

        self.assertEqual(tuple(port.key for port in if_node.output_ports), ("true", "false"))
        self.assertEqual(
            tuple(port.key for port in switch_node.output_ports),
            ("case_1", "case_2", "case_3", "case_4", "case_5", "fallback"),
        )

    def test_designer_catalog_payload_includes_typed_field_and_docs_metadata(self):
        payload = build_workflow_catalog_payload()

        openai_definition = next(
            item for item in payload["definitions"] if item["type"] == "openai.model.chat"
        )
        model_field = next(field for field in openai_definition["fields"] if field["key"] == "model")
        system_prompt_field = next(
            field for field in openai_definition["fields"] if field["key"] == "system_prompt"
        )

        self.assertEqual(openai_definition["mode"], "action")
        self.assertEqual(openai_definition["resource"], "chat")
        self.assertEqual(openai_definition["operation"], "complete")
        self.assertEqual(openai_definition["capabilities"], ["agent:model"])
        self.assertEqual(
            openai_definition["connection_slots"][0]["description"],
            "Optional reusable OpenAI connection used for authenticated model requests.",
        )
        self.assertTrue(model_field["required"])
        self.assertEqual(model_field["value_type"], "string")
        self.assertEqual(model_field["description"], "OpenAI model identifier to execute.")
        self.assertEqual(system_prompt_field["binding"], "template")
        self.assertEqual(payload["presentation"]["settings"]["controls"]["required_badge"], "Required")
        self.assertEqual(payload["presentation"]["settings"]["groups"]["connection"]["title"], "Connection")
        self.assertEqual(payload["presentation"]["settings"]["groups"]["docs"]["fields"]["capabilities"], "Capabilities")
        self.assertEqual(payload["presentation"]["execution"]["inspector"]["tabs"]["steps"], "Steps")
        self.assertEqual(
            payload["presentation"]["execution"]["inspector"]["overview"]["last_completed_node"],
            "Last completed",
        )
        self.assertEqual(openai_definition["typeVersion"], 1)

    def test_core_designer_payload_exposes_standardized_metadata(self):
        payload = build_workflow_catalog_payload()

        set_definition = next(item for item in payload["definitions"] if item["type"] == "core.set")
        response_definition = next(item for item in payload["definitions"] if item["type"] == "core.response")
        if_definition = next(item for item in payload["definitions"] if item["type"] == "core.if")
        switch_definition = next(item for item in payload["definitions"] if item["type"] == "core.switch")
        webhook_definition = next(item for item in payload["definitions"] if item["type"] == "core.webhook_trigger")

        output_key_field = next(field for field in set_definition["fields"] if field["key"] == "output_key")
        fields_field = next(field for field in set_definition["fields"] if field["key"] == "fields")
        status_field = next(field for field in response_definition["fields"] if field["key"] == "status")
        conditions_field = next(field for field in if_definition["fields"] if field["key"] == "conditions")
        combinator_field = next(field for field in if_definition["fields"] if field["key"] == "combinator")
        rules_field = next(field for field in switch_definition["fields"] if field["key"] == "rules")
        http_method_field = next(field for field in webhook_definition["fields"] if field["key"] == "http_method")
        authentication_field = next(field for field in webhook_definition["fields"] if field["key"] == "authentication")
        response_mode_field = next(field for field in webhook_definition["fields"] if field["key"] == "response_mode")
        secret_field = next(field for field in webhook_definition["fields"] if field["key"] == "secret_name")

        self.assertEqual(set_definition["defaultName"], "Edit Fields")
        self.assertEqual(set_definition["subtitle"], "={{config.output_key}}")
        self.assertEqual(set_definition["nodeGroup"], ["input"])
        self.assertTrue(output_key_field["no_data_expression"])
        self.assertEqual(output_key_field["ui_group"], "result")
        self.assertEqual(fields_field["type"], "fixed_collection")
        self.assertEqual(fields_field["collection_options"][0]["key"], "values")
        self.assertTrue(status_field["is_node_setting"])
        self.assertEqual(status_field["ui_group"], "advanced")
        self.assertEqual(conditions_field["value_type"], "object")
        self.assertEqual(conditions_field["type"], "fixed_collection")
        self.assertEqual(conditions_field["collection_options"][0]["fields"][0]["key"], "leftPath")
        self.assertEqual(conditions_field["ui_group"], "input")
        self.assertEqual(combinator_field["type"], "select")
        self.assertEqual(rules_field["type"], "fixed_collection")
        self.assertEqual(http_method_field["type"], "select")
        self.assertEqual(http_method_field["value_type"], "string")
        self.assertEqual(authentication_field["type"], "select")
        self.assertEqual(authentication_field["value_type"], "string")
        self.assertEqual(response_mode_field["type"], "select")
        self.assertEqual(response_mode_field["value_type"], "string")
        self.assertEqual(secret_field["visible_when"], {"authentication": ["secret_header"]})
