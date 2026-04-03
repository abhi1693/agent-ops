import os
from json import loads
from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from automation.models import Secret, SecretGroup, Workflow
from tenancy.models import Environment, Organization, Workspace
from users.models import Membership, ObjectPermission, User


class _FakeJsonResponse:
    def __init__(self, payload, *, status=200, content_type="application/json", headers=None, raw_body=None):
        self._payload = payload
        self._status = status
        self._raw_body = raw_body
        self.headers = {"Content-Type": content_type, **(headers or {})}

    def read(self):
        import json

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
                "config": {
                    "template": "Triage {{ trigger.payload.ticket_id|default:'manual' }}",
                    "secret_name": "OPENAI_API_KEY",
                },
                "position": {"x": 336, "y": 56},
            },
            {
                "id": "model-1",
                "kind": "tool",
                "type": "tool.openai_chat_model",
                "label": "OpenAI chat model",
                "config": {
                    "secret_name": "OPENAI_API_KEY",
                },
                "position": {"x": 336, "y": 224},
            },
        ],
        "edges": [
            {"id": "edge-1", "source": "trigger-1", "target": "agent-1"},
            {
                "id": "edge-2",
                "source": "model-1",
                "sourcePort": "ai_languageModel",
                "target": "agent-1",
                "targetPort": "ai_languageModel",
            },
        ],
    }


class WorkflowAPITests(TestCase):
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
            definition=_definition("New task"),
        )
        self.other_workflow = Workflow.objects.create(
            environment=self.other_environment,
            name="Security escalation",
            definition=_definition("Suspicious activity"),
        )

    def test_automation_api_root_is_available_for_scoped_members(self):
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("api:automation-api:api-root"))

        self.assertEqual(response.status_code, 200)

    def test_automation_api_root_lists_endpoints_for_staff(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("api:automation-api:api-root"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "workflows": "http://testserver/api/automation/workflows/",
                "secrets": "http://testserver/api/automation/secrets/",
                "secret-groups": "http://testserver/api/automation/secret-groups/",
            },
        )

    def test_workflow_create_derives_scope_from_environment(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("api:automation-api:workflow-list"),
            {
                "environment": self.environment.pk,
                "name": "Lead enrichment",
                "description": "Qualify inbound leads with agents and tools.",
                "enabled": True,
                "definition": _definition("New lead"),
                "metadata": {"category": "sales"},
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["environment"]["id"], self.environment.pk)
        self.assertEqual(payload["workspace"]["id"], self.workspace.pk)
        self.assertEqual(payload["organization"]["id"], self.organization.pk)
        self.assertEqual(payload["node_count"], 3)
        self.assertEqual(payload["edge_count"], 2)

    def test_scoped_member_only_lists_workflows_inside_active_scope(self):
        self.client.force_login(self.standard_user)

        response = self.client.get(reverse("api:automation-api:workflow-list"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["id"], self.workflow.id)

    def test_scoped_member_cannot_create_workflow_without_add_permission(self):
        self.client.force_login(self.standard_user)

        response = self.client.post(
            reverse("api:automation-api:workflow-list"),
            {
                "organization": self.organization.pk,
                "name": "Shared workflow",
                "enabled": True,
                "definition": _definition("Trigger"),
                "metadata": {},
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_scoped_member_can_create_workflow_with_add_permission(self):
        permission = ObjectPermission.objects.create(
            name="Scoped workflow add",
            actions=["add"],
            constraints={"organization": "$organization"},
        )
        permission.content_types.add(self.workflow_content_type)
        self.membership.object_permissions.add(permission)
        self.client.force_login(self.standard_user)

        response = self.client.post(
            reverse("api:automation-api:workflow-list"),
            {
                "organization": self.organization.pk,
                "name": "Shared workflow",
                "enabled": True,
                "definition": _definition("Trigger"),
                "metadata": {"category": "shared"},
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["organization"]["id"], self.organization.pk)
        self.assertTrue(
            Workflow.objects.filter(
                organization=self.organization,
                name="Shared workflow",
            ).exists()
        )

    def test_workflow_execute_action_returns_persisted_run(self):
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
                        "secret_name": "OPENAI_API_KEY",
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
                {
                    "id": "model-1",
                    "kind": "tool",
                    "type": "tool.openai_chat_model",
                    "label": "OpenAI chat model",
                    "config": {
                        "secret_name": "OPENAI_API_KEY",
                    },
                    "position": {"x": 320, "y": 240},
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
        secret_group = SecretGroup.objects.create(
            environment=self.environment,
            name="workflow-api-secrets",
        )
        self.workflow.secret_group = secret_group
        self.workflow.save(update_fields=("secret_group",))
        Secret.objects.create(
            secret_group=secret_group,
            provider="environment-variable",
            name="OPENAI_API_KEY",
            parameters={"variable": "OPENAI_API_KEY"},
        )
        self.client.force_login(self.staff_user)

        def fake_urlopen(request, timeout=20):
            self.assertEqual(timeout, 20)
            body = loads(request.data.decode("utf-8"))
            self.assertEqual(body["messages"][0]["content"], "Review T-42")
            return _FakeJsonResponse(
                {
                    "id": "chatcmpl-api-1",
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
                    reverse("api:automation-api:workflow-execute", args=[self.workflow.pk]),
                    {
                        "input_data": {"ticket_id": "T-42"},
                    },
                    content_type="application/json",
                )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["status"], "succeeded")
        self.assertEqual(payload["output_data"]["response"], "Completed Review T-42")
