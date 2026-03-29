from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from core.models import PrimaryModel
from integrations.models import Secret
from integrations.secrets import get_secrets_provider
from tenancy.models import Environment, Organization, Workspace


class SecretModelInheritanceTests(TestCase):
    def test_secret_inherits_primary_model(self):
        self.assertTrue(issubclass(Secret, PrimaryModel))

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
