import hashlib
import hmac
import json
import os
from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from automation.models import Workflow, WorkflowRun
from integrations.models import Secret, SecretGroup, SecretGroupAssignment
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
        self.assertContains(response, "Workflow canvas")
        self.assertContains(response, "Add node")
        self.assertContains(response, '<optgroup label="Built-ins">')
        self.assertContains(response, '<optgroup label="AgentOps utilities">')
        self.assertContains(response, '<optgroup label="GitHub">')
        self.assertContains(response, '<optgroup label="Observability">')
        self.assertContains(response, '<option value="n8n-nodes-base.manualTrigger">Manual Trigger</option>', html=True)
        self.assertContains(response, '<option value="n8n-nodes-base.scheduleTrigger">Schedule Trigger</option>', html=True)
        self.assertContains(response, '<option value="agent">Agent</option>', html=True)
        self.assertContains(response, '<option value="n8n-nodes-base.set">Set</option>', html=True)
        self.assertContains(response, '<option value="n8n-nodes-base.if">If</option>', html=True)
        self.assertContains(response, '<option value="n8n-nodes-base.switch">Switch</option>', html=True)
        self.assertContains(response, '<option value="response">Response</option>', html=True)
        self.assertContains(response, '<option value="n8n-nodes-base.stopAndError">Stop and Error</option>', html=True)
        self.assertContains(response, '<option value="trigger.github">GitHub</option>', html=True)
        self.assertContains(response, '<option value="trigger.alertmanager_webhook">Alertmanager webhook</option>', html=True)
        self.assertContains(response, '<option value="trigger.kibana_webhook">Kibana webhook</option>', html=True)
        self.assertContains(response, '<option value="tool.prometheus_query">Prometheus query</option>', html=True)
        self.assertContains(response, '<option value="tool.elasticsearch_search">Elasticsearch search</option>', html=True)
        self.assertContains(response, '<option value="tool.template">Render template</option>', html=True)
        self.assertContains(response, '&quot;type&quot;: &quot;n8n-nodes-base.manualTrigger&quot;')
        self.assertContains(response, '<option value="trigger-1">New task</option>', html=True)
        self.assertContains(response, '<option value="agent-1">Triage agent</option>', html=True)
        self.assertContains(response, "Add at least two nodes before creating a connection.")

    def test_workflow_designer_includes_secret_group_options_for_auth_nodes(self):
        SecretGroup.objects.create(
            environment=self.environment,
            name="Shared node auth",
        )
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("workflow_designer", args=[self.workflow.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Auth secret group")
        self.assertContains(response, "No secret group")
        self.assertContains(response, "Shared node auth")

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
        self.assertEqual(self.workflow.node_count, 3)
        self.assertEqual(self.workflow.edge_count, 2)
        self.assertEqual(self.workflow.definition["nodes"][0]["type"], "n8n-nodes-base.manualTrigger")
        self.assertEqual(self.workflow.definition["nodes"][1]["type"], "agent")
        self.assertEqual(self.workflow.definition["nodes"][1]["label"], "Planner")
        self.assertEqual(self.workflow.definition["nodes"][2]["type"], "response")

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
            ],
        }
        self.workflow.save(update_fields=("definition",))
        Secret.objects.create(
            environment=self.environment,
            provider="environment-variable",
            name="OPENAI_API_KEY",
            parameters={"variable": "OPENAI_API_KEY"},
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
                            "webhook_secret_name": "ALERTMANAGER_WEBHOOK_SECRET",
                            "webhook_secret_provider": "environment-variable",
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
        Secret.objects.create(
            environment=self.environment,
            provider="environment-variable",
            name="ALERTMANAGER_WEBHOOK_SECRET",
            parameters={"variable": "ALERTMANAGER_WEBHOOK_SECRET"},
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
                            "webhook_secret_name": "KIBANA_WEBHOOK_SECRET",
                            "webhook_secret_provider": "environment-variable",
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
        Secret.objects.create(
            environment=self.environment,
            provider="environment-variable",
            name="KIBANA_WEBHOOK_SECRET",
            parameters={"variable": "KIBANA_WEBHOOK_SECRET"},
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
                        "type": "trigger.github",
                        "label": "GitHub",
                        "config": {
                            "signature_secret_name": "GITHUB_WEBHOOK_SECRET",
                            "signature_secret_provider": "environment-variable",
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
        Secret.objects.create(
            environment=self.environment,
            provider="environment-variable",
            name="GITHUB_WEBHOOK_SECRET",
            parameters={"variable": "GITHUB_WEBHOOK_SECRET"},
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

    def test_workflow_webhook_trigger_resolves_grouped_secret_for_signature_validation(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="GitHub webhook grouped secret",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "type": "trigger.github",
                        "label": "GitHub",
                        "config": {
                            "auth_secret_group_id": "",
                            "signature_secret_name": "webhook_secret",
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
            environment=self.environment,
            provider="environment-variable",
            name="GITHUB_WEBHOOK_SECRET",
            parameters={"variable": "GITHUB_WEBHOOK_SECRET"},
        )
        secret_group = SecretGroup.objects.create(
            environment=self.environment,
            name="GitHub auth",
        )
        SecretGroupAssignment.objects.create(
            secret_group=secret_group,
            secret=secret,
            key="webhook_secret",
            order=10,
        )
        workflow.definition["nodes"][0]["config"]["auth_secret_group_id"] = str(secret_group.pk)
        workflow.save(update_fields=("definition",))
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
                        "type": "trigger.github",
                        "label": "GitHub",
                        "config": {
                            "signature_secret_name": "GITHUB_WEBHOOK_SECRET",
                            "signature_secret_provider": "environment-variable",
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
        Secret.objects.create(
            environment=self.environment,
            provider="environment-variable",
            name="GITHUB_WEBHOOK_SECRET",
            parameters={"variable": "GITHUB_WEBHOOK_SECRET"},
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
