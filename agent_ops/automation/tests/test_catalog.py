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
        self.assertEqual(registry["capability_index"][CAPABILITY_TRIGGER_WEBHOOK], {"github.trigger.webhook"})
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
