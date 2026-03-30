from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from core.models import PrimaryModel
from integrations.models import Secret, SecretGroup, SecretGroupAssignment
from integrations.secrets import get_secrets_provider
from tenancy.models import Environment, Organization, Workspace


class SecretModelInheritanceTests(TestCase):
    def test_secret_inherits_primary_model(self):
        self.assertTrue(issubclass(Secret, PrimaryModel))

    def test_secret_group_inherits_primary_model(self):
        self.assertTrue(issubclass(SecretGroup, PrimaryModel))

    def test_secret_group_assignment_is_change_logged(self):
        from core.models import ChangeLoggedModel

        self.assertTrue(issubclass(SecretGroupAssignment, ChangeLoggedModel))

    def test_environment_variable_provider_is_registered(self):
        self.assertIsNotNone(get_secrets_provider("environment-variable"))


class SecretScopeModelTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Acme")
        self.workspace = Workspace.objects.create(
            organization=self.organization,
            name="Operations",
        )
        self.environment = Environment.objects.create(
            workspace=self.workspace,
            name="production",
        )
        self.other_workspace = Workspace.objects.create(
            organization=self.organization,
            name="Shared Services",
        )

    def test_secret_derives_scope_from_environment(self):
        secret = Secret(
            provider="environment-variable",
            environment=self.environment,
            name="github-app-client-secret",
            parameters={"variable": "GITHUB_APP_CLIENT_SECRET"},
        )

        secret.full_clean()
        secret.save()

        self.assertEqual(secret.workspace, self.workspace)
        self.assertEqual(secret.organization, self.organization)

    def test_secret_requires_unique_provider_name_per_scope(self):
        Secret.objects.create(
            provider="environment-variable",
            environment=self.environment,
            name="github-app-client-secret",
            parameters={"variable": "GITHUB_APP_CLIENT_SECRET"},
        )
        duplicate = Secret(
            provider="environment-variable",
            environment=self.environment,
            name="github-app-client-secret",
            parameters={"variable": "GITHUB_APP_CLIENT_SECRET_V2"},
        )

        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_secret_requires_registered_provider(self):
        secret = Secret(
            provider="vault-kv",
            environment=self.environment,
            name="github-app-client-secret",
            parameters={"path": "kv/data/github/prod"},
        )

        with self.assertRaises(ValidationError):
            secret.full_clean()

    def test_secret_validates_provider_parameters(self):
        secret = Secret(
            provider="environment-variable",
            environment=self.environment,
            name="github-app-client-secret",
            parameters={"path": "kv/data/github/prod"},
        )

        with self.assertRaises(ValidationError):
            secret.full_clean()

    def test_secret_database_constraint_prevents_duplicates_without_full_clean(self):
        Secret.objects.create(
            provider="environment-variable",
            organization=self.organization,
            name="shared-token",
            parameters={"variable": "SHARED_TOKEN"},
        )

        with self.assertRaises(IntegrityError):
            Secret.objects.create(
                provider="environment-variable",
                organization=self.organization,
                name="shared-token",
                parameters={"variable": "SHARED_TOKEN_V2"},
            )


class SecretGroupScopeModelTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Acme")
        self.workspace = Workspace.objects.create(
            organization=self.organization,
            name="Operations",
        )
        self.environment = Environment.objects.create(
            workspace=self.workspace,
            name="production",
        )

    def test_secret_group_derives_scope_from_environment(self):
        secret_group = SecretGroup(
            environment=self.environment,
            name="github-production",
            description="GitHub credentials",
        )

        secret_group.full_clean()
        secret_group.save()

        self.assertEqual(secret_group.workspace, self.workspace)
        self.assertEqual(secret_group.organization, self.organization)

    def test_secret_group_requires_unique_name_per_scope(self):
        SecretGroup.objects.create(
            environment=self.environment,
            name="github-production",
            description="Primary",
        )
        duplicate = SecretGroup(
            environment=self.environment,
            name="github-production",
            description="Duplicate",
        )

        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_secret_group_database_constraint_prevents_duplicates_without_full_clean(self):
        SecretGroup.objects.create(
            organization=self.organization,
            name="shared-platform",
            description="Shared credentials",
        )

        with self.assertRaises(IntegrityError):
            SecretGroup.objects.create(
                organization=self.organization,
                name="shared-platform",
                description="Duplicate shared credentials",
            )


class SecretGroupAssignmentModelTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Acme")
        self.workspace = Workspace.objects.create(
            organization=self.organization,
            name="Operations",
        )
        self.environment = Environment.objects.create(
            workspace=self.workspace,
            name="production",
        )
        self.secret_group = SecretGroup.objects.create(
            environment=self.environment,
            name="github-production",
        )
        self.secret = Secret.objects.create(
            provider="environment-variable",
            environment=self.environment,
            name="github-app-client-secret",
            parameters={"variable": "GITHUB_APP_CLIENT_SECRET"},
        )

    def test_assignment_derives_scope_from_secret_group(self):
        assignment = SecretGroupAssignment(
            secret_group=self.secret_group,
            secret=self.secret,
            key="client-secret",
        )

        assignment.full_clean()
        assignment.save()

        self.assertEqual(assignment.organization, self.organization)
        self.assertEqual(assignment.workspace, self.workspace)
        self.assertEqual(assignment.environment, self.environment)

    def test_assignment_requires_secret_to_match_group_scope(self):
        other_workspace = Workspace.objects.create(
            organization=self.organization,
            name="Security",
        )
        other_environment = Environment.objects.create(
            workspace=other_workspace,
            name="staging",
        )
        other_secret = Secret.objects.create(
            provider="environment-variable",
            environment=other_environment,
            name="slack-bot-token",
            parameters={"variable": "SLACK_BOT_TOKEN"},
        )
        assignment = SecretGroupAssignment(
            secret_group=self.secret_group,
            secret=other_secret,
            key="token",
        )

        with self.assertRaises(ValidationError):
            assignment.full_clean()

    def test_assignment_requires_unique_key_per_group(self):
        SecretGroupAssignment.objects.create(
            secret_group=self.secret_group,
            secret=self.secret,
            key="client-secret",
        )
        other_secret = Secret.objects.create(
            provider="environment-variable",
            environment=self.environment,
            name="github-webhook-secret",
            parameters={"variable": "GITHUB_WEBHOOK_SECRET"},
        )
        duplicate = SecretGroupAssignment(
            secret_group=self.secret_group,
            secret=other_secret,
            key="client-secret",
        )

        with self.assertRaises(ValidationError):
            duplicate.full_clean()
