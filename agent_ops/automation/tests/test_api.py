from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from automation.models import Workflow
from tenancy.models import Environment, Organization, Workspace
from users.models import Membership, ObjectPermission, User


def _definition(label):
    return {
        "nodes": [
            {
                "id": "trigger-1",
                "kind": "trigger",
                "label": label,
                "position": {"x": 48, "y": 56},
            },
            {
                "id": "agent-1",
                "kind": "agent",
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
        self.assertEqual(payload["node_count"], 2)
        self.assertEqual(payload["edge_count"], 1)

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
                    "label": "Manual",
                    "position": {"x": 32, "y": 40},
                },
                {
                    "id": "agent-1",
                    "kind": "agent",
                    "label": "Draft",
                    "config": {
                        "template": "Review {{ trigger.payload.ticket_id }}",
                        "output_key": "draft",
                    },
                    "position": {"x": 320, "y": 40},
                },
                {
                    "id": "response-1",
                    "kind": "response",
                    "label": "Done",
                    "config": {
                        "template": "Completed {{ draft }}",
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
        self.client.force_login(self.staff_user)

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
