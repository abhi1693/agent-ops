from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models import OrganizationalModel, PrimaryModel
from tenancy.models import Environment, Organization, Workspace


class TenancyModelTests(TestCase):
    def test_organization_inherits_organizational_model(self):
        self.assertTrue(issubclass(Organization, OrganizationalModel))

    def test_workspace_and_environment_inherit_primary_model(self):
        self.assertTrue(issubclass(Workspace, PrimaryModel))
        self.assertTrue(issubclass(Environment, PrimaryModel))

    def test_environment_inherits_organization_from_workspace(self):
        organization = Organization.objects.create(name="Acme")
        workspace = Workspace.objects.create(name="Operations", organization=organization)
        environment = Environment(workspace=workspace, name="production")

        environment.full_clean()
        environment.save()

        self.assertEqual(environment.organization, organization)

    def test_environment_rejects_workspace_from_other_organization(self):
        primary_organization = Organization.objects.create(name="Acme")
        secondary_organization = Organization.objects.create(name="Globex")
        workspace = Workspace.objects.create(name="Operations", organization=primary_organization)
        environment = Environment(
            workspace=workspace,
            organization=secondary_organization,
            name="production",
        )

        with self.assertRaises(ValidationError):
            environment.full_clean()
