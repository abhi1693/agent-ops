import hashlib
import hmac
import json
import os
from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from automation.models import Workflow, WorkflowRun
from automation.models import Secret, SecretGroup
from tenancy.models import Environment, Organization, Workspace
from users.models import Membership, ObjectPermission, User


class _FakeJsonResponse:
    def __init__(self, payload, *, status=200, content_type="application/json", headers=None, raw_body=None):
        self._payload = payload
        self._status = status
        self._raw_body = raw_body
        self.headers = {"Content-Type": content_type, **(headers or {})}

    def read(self):
        if self._raw_body is not None:
            return self._raw_body
        return json.dumps(self._payload).encode("utf-8")

    def getcode(self):
        return self._status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _definition(label):
    return {
        "nodes": [
            {
                "id": "trigger-1",
                "kind": "trigger",
                "type": "n8n-nodes-base.manualTrigger",
                "label": label,
                "position": {"x": 48, "y": 56},
            },
            {
                "id": "agent-1",
                "kind": "agent",
                "type": "agent",
                "label": "Triage agent",
                "position": {"x": 336, "y": 56},
            },
        ],
        "edges": [
            {
                "id": "edge-1",
                "source": "trigger-1",
                "target": "agent-1",
            }
        ],
    }


class WorkflowViewTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="operator",
            email="operator@example.com",
            password="correct-horse-battery-staple",
            is_staff=True,
        )
        self.standard_user = User.objects.create_user(
            username="viewer",
            email="viewer@example.com",
            password="correct-horse-battery-staple",
        )
        self.organization = Organization.objects.create(name="Acme", description="Primary tenant")
        self.workspace = Workspace.objects.create(
            organization=self.organization,
            name="Operations",
            description="Operational workspace",
        )
        self.environment = Environment.objects.create(
            workspace=self.workspace,
            name="production",
            description="Production environment",
        )
        self.other_organization = Organization.objects.create(name="Beta", description="Secondary tenant")
        self.other_workspace = Workspace.objects.create(
            organization=self.other_organization,
            name="Security",
            description="Security workspace",
        )
        self.other_environment = Environment.objects.create(
            workspace=self.other_workspace,
            name="staging",
            description="Staging environment",
        )
        self.membership = Membership.objects.create(
            user=self.standard_user,
            organization=self.organization,
            workspace=self.workspace,
            is_default=True,
        )
        self.workflow_content_type = ContentType.objects.get_for_model(Workflow)
        self.workflow = Workflow.objects.create(
            environment=self.environment,
            name="Intake triage",
            description="Route new work into the agentic intake path.",
            definition=_definition("New task"),
        )
        self.other_workflow = Workflow.objects.create(
            environment=self.other_environment,
            name="Security escalation",
            definition=_definition("Suspicious activity"),
        )

    def _create_secret_group(self, *, name="Workflow secrets"):
        return SecretGroup.objects.create(
            environment=self.environment,
            name=name,
        )

    def _bind_secret(
        self,
        *,
        workflow,
        secret_name,
        variable_name=None,
        provider="environment-variable",
        parameters=None,
        secret_group=None,
    ):
        group = secret_group or workflow.secret_group or self._create_secret_group(name=f"{workflow.name} secrets")
        secret = Secret.objects.create(
            secret_group=group,
            provider=provider,
            name=secret_name,
            parameters=parameters or {"variable": variable_name or secret_name},
        )
        if workflow.secret_group_id != group.pk:
            workflow.secret_group = group
            workflow.save(update_fields=("secret_group",))
        return secret

    def test_workflow_list_is_scoped_for_members(self):
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("workflow_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.workflow.name)
        self.assertNotContains(response, self.other_workflow.name)

    def test_workflow_detail_shows_summary_and_designer_link(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("workflow_detail", args=[self.workflow.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.workflow.name)
        self.assertContains(response, "Open designer")
        self.assertContains(response, "Nodes")
        self.assertContains(response, "Edges")
        self.assertContains(response, "Manual run")
        self.assertContains(response, reverse("workflow_designer", args=[self.workflow.pk]))

    def test_workflow_add_requires_explicit_add_permission(self):
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("workflow_add"))

        self.assertEqual(response.status_code, 403)

    def test_workflow_add_form_uses_scoped_choices_when_permission_granted(self):
        permission = ObjectPermission.objects.create(
            name="Scoped workflow add form",
            actions=["add"],
            constraints={"organization": "$organization"},
        )
        permission.content_types.add(self.workflow_content_type)
        self.membership.object_permissions.add(permission)
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("workflow_add"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.organization.name)
        self.assertContains(response, self.workspace.name)
        self.assertContains(response, self.environment.name)
        self.assertNotContains(response, self.other_organization.name)
        self.assertNotContains(response, self.other_workspace.name)
        self.assertNotContains(response, self.other_environment.name)

    def test_workflow_add_creates_empty_draft_without_definition_errors(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("workflow_add"),
            {
                "environment": self.environment.pk,
                "name": "Draft workflow",
                "description": "Created before the graph is designed.",
                "enabled": "on",
                "metadata": "{}",
            },
        )

        workflow = Workflow.objects.get(name="Draft workflow")
        self.assertRedirects(response, workflow.get_absolute_url())
        self.assertEqual(workflow.definition["nodes"], [])
        self.assertEqual(workflow.definition["edges"], [])

    def test_workflow_designer_requires_change_permission_for_scoped_members(self):
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("workflow_designer", args=[self.workflow.pk]))

        self.assertEqual(response.status_code, 403)

    def test_workflow_designer_renders_existing_nodes_as_connection_options(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("workflow_designer", args=[self.workflow.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="workflow-definition-data"')
        self.assertContains(response, 'id="workflow-node-templates-data"')
        self.assertContains(response, "data-workflow-board")
        self.assertContains(response, "Add node")
        self.assertContains(response, '"app_label": "Built-ins"')
        self.assertContains(response, '"app_label": "AgentOps utilities"')
        self.assertContains(response, '"app_label": "GitHub"')
        self.assertContains(response, '"app_label": "Observability"')
        self.assertContains(response, '"type": "n8n-nodes-base.manualTrigger"')
        self.assertContains(response, '"type": "n8n-nodes-base.scheduleTrigger"')
        self.assertContains(response, '"type": "agent"')
        self.assertContains(response, '"type": "n8n-nodes-base.set"')
        self.assertContains(response, '"type": "n8n-nodes-base.if"')
        self.assertContains(response, '"type": "n8n-nodes-base.switch"')
        self.assertContains(response, '"type": "response"')
        self.assertContains(response, '"type": "n8n-nodes-base.stopAndError"')
        self.assertContains(response, '"type": "trigger.github_webhook"')
        self.assertContains(response, '"type": "trigger.alertmanager_webhook"')
        self.assertContains(response, '"type": "trigger.kibana_webhook"')
        self.assertContains(response, '"type": "tool.prometheus_query"')
        self.assertContains(response, '"type": "tool.elasticsearch_search"')
        self.assertContains(response, '"type": "tool.template"')
        self.assertContains(response, '"label": "New task"')
        self.assertContains(response, '"label": "Triage agent"')
        self.assertContains(response, 'data-workflow-run')
        self.assertContains(response, 'data-workflow-execution-status')
        self.assertContains(response, reverse("workflow_designer_run", args=[self.workflow.pk]))
        self.assertContains(response, reverse("workflow_designer_node_run", args=[self.workflow.pk, "__node_id__"]))

    def test_workflow_designer_renders_scoped_secret_group_options_for_nodes(self):
        SecretGroup.objects.create(
            environment=self.environment,
            name="Shared node auth",
        )
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("workflow_designer", args=[self.workflow.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Auth secret group")
        self.assertContains(response, "No secret group")
        self.assertContains(response, "Shared node auth")

    def test_workflow_designer_hydrates_secret_name_select_from_secret_groups(self):
        workflow_group = self._create_secret_group(name="Workflow auth")
        elastic_group = self._create_secret_group(name="Elastic")
        self.workflow.secret_group = workflow_group
        self.workflow.save(update_fields=("secret_group",))
        self._bind_secret(
            workflow=self.workflow,
            secret_group=workflow_group,
            secret_name="OPENAI_API_KEY",
        )
        self._bind_secret(
            workflow=self.workflow,
            secret_group=elastic_group,
            secret_name="api-key",
        )
        self.workflow.secret_group = workflow_group
        self.workflow.save(update_fields=("secret_group",))
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("workflow_designer", args=[self.workflow.pk]))

        self.assertEqual(response.status_code, 200)
        template = next(
            item
            for item in response.context["workflow_node_templates"]
            if item["type"] == "tool.elasticsearch_search"
        )
        fields_by_key = {field["key"]: field for field in template["fields"]}
        field_keys = [field["key"] for field in template["fields"]]

        self.assertLess(field_keys.index("secret_group_id"), field_keys.index("secret_name"))
        self.assertEqual(fields_by_key["secret_group_id"]["type"], "select")
        self.assertEqual(fields_by_key["secret_group_id"]["options"][0], {"value": "", "label": "Use workflow secret group"})
        self.assertIn(
            {"value": str(elastic_group.pk), "label": f"{elastic_group.name} ({elastic_group.scope_label})"},
            fields_by_key["secret_group_id"]["options"],
        )
        self.assertEqual(fields_by_key["secret_name"]["type"], "select")
        self.assertEqual(
            fields_by_key["secret_name"]["options"],
            [{"value": "OPENAI_API_KEY", "label": "OPENAI_API_KEY"}],
        )
        self.assertEqual(
            fields_by_key["secret_name"]["options_by_field"]["secret_group_id"][str(elastic_group.pk)],
            [{"value": "api-key", "label": "api-key"}],
        )

    def test_workflow_designer_updates_definition(self):
        self.client.force_login(self.staff_user)
        updated_definition = {
            "nodes": [
                {
                    "id": "trigger-1",
                    "kind": "trigger",
                    "label": "New task",
                    "type": "n8n-nodes-base.manualTrigger",
                    "position": {"x": 32, "y": 40},
                },
                {
                    "id": "agent-1",
                    "kind": "agent",
                    "label": "Planner",
                    "type": "agent",
                    "config": {
                        "template": "Plan work for {{ trigger.payload.ticket_id }}",
                        "output_key": "plan",
                    },
                    "position": {"x": 320, "y": 80},
                },
                {
                    "id": "model-1",
                    "kind": "tool",
                    "label": "OpenAI chat model",
                    "type": "tool.openai_chat_model",
                    "config": {
                        "base_url": "https://api.openai.com/v1",
                        "model": "gpt-4.1-mini",
                        "secret_name": "OPENAI_API_KEY",
                    },
                    "position": {"x": 320, "y": 240},
                },
                {
                    "id": "response-1",
                    "kind": "response",
                    "label": "Return plan",
                    "type": "response",
                    "config": {
                        "template": "Planned {{ plan }}",
                        "status": "succeeded",
                    },
                    "position": {"x": 608, "y": 80},
                },
            ],
            "edges": [
                {"id": "edge-1", "source": "trigger-1", "target": "agent-1"},
                {"id": "edge-2", "source": "agent-1", "target": "response-1"},
                {
                    "id": "edge-3",
                    "source": "model-1",
                    "sourcePort": "ai_languageModel",
                    "target": "agent-1",
                    "targetPort": "ai_languageModel",
                },
            ],
        }

        response = self.client.post(
            reverse("workflow_designer", args=[self.workflow.pk]),
            {
                "definition": json.dumps(updated_definition),
            },
        )

        self.assertRedirects(response, reverse("workflow_designer", args=[self.workflow.pk]))
        self.workflow.refresh_from_db()
        self.assertEqual(self.workflow.node_count, 4)
        self.assertEqual(self.workflow.edge_count, 3)
        self.assertEqual(self.workflow.definition["nodes"][0]["type"], "n8n-nodes-base.manualTrigger")
        self.assertEqual(self.workflow.definition["nodes"][1]["type"], "agent")
        self.assertEqual(self.workflow.definition["nodes"][1]["label"], "Planner")
        self.assertEqual(self.workflow.definition["nodes"][2]["type"], "tool.openai_chat_model")
        self.assertEqual(self.workflow.definition["nodes"][3]["type"], "response")

    def test_workflow_designer_run_endpoint_saves_definition_and_executes_workflow(self):
        self.client.force_login(self.staff_user)
        definition = {
            "nodes": [
                {
                    "id": "trigger-1",
                    "kind": "trigger",
                    "type": "n8n-nodes-base.manualTrigger",
                    "label": "Manual",
                    "position": {"x": 32, "y": 40},
                },
                {
                    "id": "response-1",
                    "kind": "response",
                    "type": "response",
                    "label": "Reply",
                    "config": {
                        "template": "Completed {{ trigger.payload.ticket_id }}",
                    },
                    "position": {"x": 320, "y": 40},
                },
            ],
            "edges": [
                {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
            ],
        }

        response = self.client.post(
            reverse("workflow_designer_run", args=[self.workflow.pk]),
            data=json.dumps(
                {
                    "definition": definition,
                    "input_data": {"ticket_id": "T-42"},
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.workflow.refresh_from_db()
        self.assertEqual(self.workflow.definition["nodes"][1]["label"], "Reply")
        self.assertEqual(payload["mode"], "workflow")
        self.assertEqual(payload["run"]["status"], "succeeded")
        self.assertIn("Completed T-42", payload["run"]["output_json"])

    def test_workflow_designer_node_run_endpoint_runs_primary_path_node(self):
        self.client.force_login(self.staff_user)
        definition = {
            "nodes": [
                {
                    "id": "trigger-1",
                    "kind": "trigger",
                    "type": "n8n-nodes-base.manualTrigger",
                    "label": "Manual",
                    "position": {"x": 32, "y": 40},
                },
                {
                    "id": "tool-1",
                    "kind": "tool",
                    "type": "tool.template",
                    "label": "Render",
                    "config": {
                        "output_key": "tool.output",
                        "template": "Service {{ trigger.payload.service }}",
                    },
                    "position": {"x": 320, "y": 40},
                },
                {
                    "id": "response-1",
                    "kind": "response",
                    "type": "response",
                    "label": "Done",
                    "config": {
                        "template": "{{ tool.output }}",
                    },
                    "position": {"x": 608, "y": 40},
                },
            ],
            "edges": [
                {"id": "edge-1", "source": "trigger-1", "target": "tool-1"},
                {"id": "edge-2", "source": "tool-1", "target": "response-1"},
            ],
        }

        response = self.client.post(
            reverse("workflow_designer_node_run", args=[self.workflow.pk, "tool-1"]),
            data=json.dumps(
                {
                    "definition": definition,
                    "input_data": {"service": "payments"},
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "node_path")
        self.assertEqual(payload["node"]["id"], "tool-1")
        self.assertEqual(payload["run"]["status"], "succeeded")
        self.assertEqual(payload["run"]["step_count"], 2)
        self.assertIn("Service payments", payload["run"]["output_json"])

    def test_workflow_designer_node_run_endpoint_runs_auxiliary_node_preview(self):
        self.client.force_login(self.staff_user)
        definition = {
            "nodes": [
                {
                    "id": "trigger-1",
                    "kind": "trigger",
                    "type": "n8n-nodes-base.manualTrigger",
                    "label": "Manual",
                    "position": {"x": 32, "y": 40},
                },
                {
                    "id": "agent-1",
                    "kind": "agent",
                    "type": "agent",
                    "label": "Draft",
                    "config": {
                        "template": "Review {{ trigger.payload.ticket_id }}",
                    },
                    "position": {"x": 320, "y": 40},
                },
                {
                    "id": "model-1",
                    "kind": "tool",
                    "type": "tool.openai_chat_model",
                    "label": "OpenAI chat model",
                    "config": {
                        "base_url": "https://api.openai.com/v1",
                        "model": "gpt-4.1-mini",
                        "secret_name": "OPENAI_API_KEY",
                    },
                    "position": {"x": 320, "y": 240},
                },
                {
                    "id": "response-1",
                    "kind": "response",
                    "type": "response",
                    "label": "Done",
                    "config": {
                        "template": "Completed",
                    },
                    "position": {"x": 608, "y": 40},
                },
            ],
            "edges": [
                {"id": "edge-1", "source": "trigger-1", "target": "agent-1"},
                {"id": "edge-2", "source": "agent-1", "target": "response-1"},
                {
                    "id": "edge-3",
                    "source": "model-1",
                    "sourcePort": "ai_languageModel",
                    "target": "agent-1",
                    "targetPort": "ai_languageModel",
                },
            ],
        }

        response = self.client.post(
            reverse("workflow_designer_node_run", args=[self.workflow.pk, "model-1"]),
            data=json.dumps(
                {
                    "definition": definition,
                    "input_data": {"ticket_id": "T-42"},
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "node_preview")
        self.assertEqual(payload["node"]["id"], "model-1")
        self.assertEqual(payload["run"]["status"], "succeeded")
        self.assertEqual(payload["run"]["step_count"], 1)
        self.assertIn("gpt-4.1-mini", payload["run"]["output_json"])

    def test_workflow_detail_post_executes_runtime_and_persists_run(self):
        self.workflow.definition = {
            "nodes": [
                {
                    "id": "trigger-1",
                    "kind": "trigger",
                    "type": "n8n-nodes-base.manualTrigger",
                    "label": "Manual",
                    "position": {"x": 32, "y": 40},
                },
                {
                    "id": "agent-1",
                    "kind": "agent",
                    "type": "agent",
                    "label": "Draft",
                    "config": {
                        "template": "Review {{ trigger.payload.ticket_id }}",
                    },
                    "position": {"x": 320, "y": 40},
                },
                {
                    "id": "model-1",
                    "kind": "tool",
                    "type": "tool.openai_chat_model",
                    "label": "OpenAI chat model",
                    "config": {
                        "base_url": "https://api.openai.com/v1",
                        "model": "gpt-4.1-mini",
                        "secret_name": "OPENAI_API_KEY",
                    },
                    "position": {"x": 320, "y": 240},
                },
                {
                    "id": "response-1",
                    "kind": "response",
                    "type": "response",
                    "label": "Done",
                    "config": {
                        "template": "Completed {{ llm.response.text }}",
                    },
                    "position": {"x": 608, "y": 40},
                },
            ],
            "edges": [
                {"id": "edge-1", "source": "trigger-1", "target": "agent-1"},
                {"id": "edge-2", "source": "agent-1", "target": "response-1"},
                {
                    "id": "edge-3",
                    "source": "model-1",
                    "sourcePort": "ai_languageModel",
                    "target": "agent-1",
                    "targetPort": "ai_languageModel",
                },
            ],
        }
        self.workflow.save(update_fields=("definition",))
        self._bind_secret(
            workflow=self.workflow,
            secret_name="OPENAI_API_KEY",
        )
        self.client.force_login(self.staff_user)

        def fake_urlopen(request, timeout=20):
            self.assertEqual(timeout, 20)
            body = json.loads(request.data.decode("utf-8"))
            self.assertEqual(body["messages"][0]["content"], "Review T-42")
            return _FakeJsonResponse(
                {
                    "id": "chatcmpl-views-1",
                    "model": "gpt-4.1-mini",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "content": "Review T-42",
                            },
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
                }
            )

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai"}, clear=False):
            with patch("automation.tools.base.urlopen", side_effect=fake_urlopen):
                response = self.client.post(
                    reverse("workflow_detail", args=[self.workflow.pk]),
                    {
                        "input_data": json.dumps({"ticket_id": "T-42"}),
                    },
                )

        self.assertRedirects(response, reverse("workflow_detail", args=[self.workflow.pk]))
        run = WorkflowRun.objects.get(workflow=self.workflow)
        self.assertEqual(run.status, WorkflowRun.StatusChoices.SUCCEEDED)
        self.assertEqual(run.output_data["response"], "Completed Review T-42")

    def test_home_dashboard_includes_workflow_automation_summary_for_staff(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        stats_by_title = {section["title"]: section for section in response.context["stats"]}
        self.assertIn("Workflow Automation", stats_by_title)
        automation_items = {item["label"]: item for item in stats_by_title["Workflow Automation"]["items"]}
        self.assertEqual(automation_items["Workflows"]["count"], 2)

    def test_home_dashboard_scopes_workflow_automation_summary_for_members(self):
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        stats_by_title = {section["title"]: section for section in response.context["stats"]}
        self.assertIn("Workflow Automation", stats_by_title)
        automation_items = {item["label"]: item for item in stats_by_title["Workflow Automation"]["items"]}
        self.assertEqual(automation_items["Workflows"]["count"], 1)
        self.assertContains(response, "Workflows")

    def test_workflow_webhook_trigger_accepts_alertmanager_payload(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Alertmanager webhook",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "trigger.alertmanager_webhook",
                        "label": "Alertmanager",
                        "config": {
                            "secret_name": "ALERTMANAGER_WEBHOOK_SECRET",
                        },
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "response",
                        "label": "Done",
                        "config": {
                            "template": "{{ trigger.meta.source }}:{{ trigger.payload.receiver }}",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
                ],
            },
        )
        self._bind_secret(
            workflow=workflow,
            secret_name="ALERTMANAGER_WEBHOOK_SECRET",
        )

        with patch.dict(os.environ, {"ALERTMANAGER_WEBHOOK_SECRET": "alert-secret"}, clear=False):
            response = self.client.post(
                reverse("workflow_webhook_trigger", args=[workflow.pk]),
                data=json.dumps({"receiver": "platform-pager"}),
                content_type="application/json",
                HTTP_X_AGENTOPS_WEBHOOK_SECRET="alert-secret",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "succeeded")
        self.assertEqual(payload["output_data"]["response"], "alertmanager_webhook:platform-pager")
        run = WorkflowRun.objects.get(pk=payload["run_id"])
        self.assertEqual(run.trigger_mode, "alertmanager_webhook")

    def test_workflow_webhook_trigger_accepts_kibana_payload(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Kibana webhook",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "trigger.kibana_webhook",
                        "label": "Kibana",
                        "config": {
                            "secret_name": "KIBANA_WEBHOOK_SECRET",
                        },
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "response",
                        "label": "Done",
                        "config": {
                            "template": "{{ trigger.meta.source }}:{{ trigger.payload.rule.name }}",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
                ],
            },
        )
        self._bind_secret(
            workflow=workflow,
            secret_name="KIBANA_WEBHOOK_SECRET",
        )

        with patch.dict(os.environ, {"KIBANA_WEBHOOK_SECRET": "kibana-secret"}, clear=False):
            response = self.client.post(
                reverse("workflow_webhook_trigger", args=[workflow.pk]),
                data=json.dumps({"rule": {"name": "CPU high"}}),
                content_type="application/json",
                HTTP_X_AGENTOPS_WEBHOOK_SECRET="kibana-secret",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "succeeded")
        self.assertEqual(payload["output_data"]["response"], "kibana_webhook:CPU high")

    def test_workflow_webhook_trigger_accepts_github_payload_with_valid_signature(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="GitHub webhook",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "trigger.github_webhook",
                        "label": "GitHub",
                        "config": {
                            "secret_name": "GITHUB_WEBHOOK_SECRET",
                            "events": "push",
                        },
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "response",
                        "label": "Done",
                        "config": {
                            "template": "{{ trigger.meta.event }}:{{ trigger.payload.repository.full_name }}",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
                ],
            },
        )
        self._bind_secret(
            workflow=workflow,
            secret_name="GITHUB_WEBHOOK_SECRET",
        )
        body = json.dumps({"repository": {"full_name": "acme/platform"}}).encode("utf-8")

        with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": "github-secret"}, clear=False):
            signature = "sha256=" + hmac.new(
                b"github-secret",
                body,
                hashlib.sha256,
            ).hexdigest()
            response = self.client.post(
                reverse("workflow_webhook_trigger", args=[workflow.pk]),
                data=body,
                content_type="application/json",
                HTTP_X_HUB_SIGNATURE_256=signature,
                HTTP_X_GITHUB_EVENT="push",
                HTTP_X_GITHUB_DELIVERY="delivery-1",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "succeeded")
        self.assertEqual(payload["output_data"]["response"], "push:acme/platform")
        run = WorkflowRun.objects.get(pk=payload["run_id"])
        self.assertEqual(run.context_data["trigger"]["meta"]["event"], "push")

    def test_workflow_webhook_trigger_resolves_bound_secret_for_signature_validation(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="GitHub webhook grouped secret",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "trigger.github_webhook",
                        "label": "GitHub",
                        "config": {
                            "secret_name": "GITHUB_WEBHOOK_SECRET",
                            "events": "push",
                        },
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "response",
                        "label": "Done",
                        "config": {
                            "template": "{{ trigger.meta.event }}:{{ trigger.payload.repository.full_name }}",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
                ],
            },
        )
        secret = Secret.objects.create(
            secret_group=self._create_secret_group(name="GitHub auth"),
            provider="environment-variable",
            name="GITHUB_WEBHOOK_SECRET",
            parameters={"variable": "GITHUB_WEBHOOK_SECRET"},
        )
        workflow.secret_group = secret.secret_group
        workflow.save(update_fields=("secret_group",))
        body = json.dumps({"repository": {"full_name": "acme/platform"}}).encode("utf-8")

        with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": "github-secret"}, clear=False):
            signature = "sha256=" + hmac.new(
                b"github-secret",
                body,
                hashlib.sha256,
            ).hexdigest()
            response = self.client.post(
                reverse("workflow_webhook_trigger", args=[workflow.pk]),
                data=body,
                content_type="application/json",
                HTTP_X_HUB_SIGNATURE_256=signature,
                HTTP_X_GITHUB_EVENT="push",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "succeeded")
        self.assertEqual(payload["output_data"]["response"], "push:acme/platform")

    def test_workflow_webhook_trigger_rejects_invalid_github_signature(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="GitHub webhook invalid",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "trigger.github_webhook",
                        "label": "GitHub",
                        "config": {
                            "secret_name": "GITHUB_WEBHOOK_SECRET",
                        },
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "type": "response",
                        "label": "Done",
                        "position": {"x": 320, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "response-1"},
                ],
            },
        )
        self._bind_secret(
            workflow=workflow,
            secret_name="GITHUB_WEBHOOK_SECRET",
        )

        with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": "github-secret"}, clear=False):
            response = self.client.post(
                reverse("workflow_webhook_trigger", args=[workflow.pk]),
                data=json.dumps({"zen": "fail"}),
                content_type="application/json",
                HTTP_X_HUB_SIGNATURE_256="sha256=bad",
                HTTP_X_GITHUB_EVENT="push",
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("signature validation failed", response.json()["detail"].lower())
