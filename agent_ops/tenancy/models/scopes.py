from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse

from core.models import OrganizationalModel, PrimaryModel


class Organization(OrganizationalModel):
    def get_absolute_url(self):
        return reverse("organization_detail", args=[self.pk])


class Workspace(PrimaryModel):
    organization = models.ForeignKey(
        "tenancy.Organization",
        on_delete=models.CASCADE,
        related_name="workspaces",
    )
    name = models.CharField(max_length=150)

    class Meta:
        ordering = ("organization__name", "name")
        constraints = (
            models.UniqueConstraint(
                fields=("organization", "name"),
                name="tenancy_workspace_unique_organization_name",
            ),
        )

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self):
        return reverse("workspace_detail", args=[self.pk])

    def get_changelog_related_object(self):
        return self.organization


class Environment(PrimaryModel):
    organization = models.ForeignKey(
        "tenancy.Organization",
        on_delete=models.CASCADE,
        related_name="environments",
        blank=True,
        null=True,
    )
    workspace = models.ForeignKey(
        "tenancy.Workspace",
        on_delete=models.CASCADE,
        related_name="environments",
    )
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ("workspace__organization__name", "workspace__name", "name")
        constraints = (
            models.UniqueConstraint(
                fields=("workspace", "name"),
                name="tenancy_environment_unique_workspace_name",
            ),
        )

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self):
        return reverse("environment_detail", args=[self.pk])

    def clean(self):
        super().clean()

        if self.workspace_id is None:
            return

        expected_organization = self.workspace.organization
        if self.organization_id and self.organization_id != expected_organization.pk:
            raise ValidationError(
                {
                    "organization": "Organization must match the selected workspace.",
                    "workspace": "Workspace belongs to a different organization.",
                }
            )

        self.organization = expected_organization

    def save(self, *args, **kwargs):
        if self.workspace_id:
            self.organization = self.workspace.organization
        return super().save(*args, **kwargs)

    def get_changelog_related_object(self):
        return self.workspace
