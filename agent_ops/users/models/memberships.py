from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse

from core.models import PrimaryModel


class Membership(PrimaryModel):
    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    organization = models.ForeignKey(
        "tenancy.Organization",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    workspace = models.ForeignKey(
        "tenancy.Workspace",
        on_delete=models.CASCADE,
        related_name="memberships",
        blank=True,
        null=True,
    )
    environment = models.ForeignKey(
        "tenancy.Environment",
        on_delete=models.CASCADE,
        related_name="memberships",
        blank=True,
        null=True,
    )
    groups = models.ManyToManyField(
        "users.Group",
        blank=True,
        related_name="memberships",
    )
    object_permissions = models.ManyToManyField(
        "users.ObjectPermission",
        blank=True,
        related_name="memberships",
    )
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = (
            "user__username",
            "organization__name",
            "workspace__name",
            "environment__name",
        )

    def __str__(self) -> str:
        return f"{self.user} @ {self.scope_label}"

    def get_absolute_url(self):
        return reverse("membership_detail", args=[self.pk])

    @property
    def scope_type(self) -> str:
        if self.environment_id:
            return "Environment"
        if self.workspace_id:
            return "Workspace"
        return "Organization"

    @property
    def scope_label(self) -> str:
        parts = [self.organization.name] if self.organization_id else []
        if self.workspace_id:
            parts.append(self.workspace.name)
        if self.environment_id:
            parts.append(self.environment.name)
        return " / ".join(parts)

    def clean(self):
        super().clean()

        if self.environment_id and not self.workspace_id:
            self.workspace = self.environment.workspace
        if self.workspace_id and not self.organization_id:
            self.organization = self.workspace.organization

        if self.workspace_id:
            expected_organization = self.workspace.organization
            if self.organization_id != expected_organization.pk:
                raise ValidationError(
                    {
                        "organization": "Organization must match the selected workspace.",
                        "workspace": "Workspace belongs to a different organization.",
                    }
                )

        if self.environment_id:
            expected_workspace = self.environment.workspace
            expected_organization = expected_workspace.organization
            if self.workspace_id != expected_workspace.pk:
                raise ValidationError(
                    {
                        "workspace": "Workspace must match the selected environment.",
                        "environment": "Environment belongs to a different workspace.",
                    }
                )
            if self.organization_id != expected_organization.pk:
                raise ValidationError(
                    {
                        "organization": "Organization must match the selected environment.",
                        "environment": "Environment belongs to a different organization.",
                    }
                )

        if self.is_default and not self.is_active:
            raise ValidationError({"is_default": "Default memberships must remain active."})

        duplicate_qs = self.__class__.objects.exclude(pk=self.pk).filter(
            user=self.user,
            organization=self.organization,
            workspace=self.workspace,
            environment=self.environment,
        )
        if duplicate_qs.exists():
            raise ValidationError("This user already has a membership for the selected scope.")

        if self.is_default and self.user_id:
            default_qs = self.__class__.objects.exclude(pk=self.pk).filter(
                user=self.user,
                is_default=True,
            )
            if default_qs.exists():
                raise ValidationError({"is_default": "Only one default membership is allowed per user."})

    def save(self, *args, **kwargs):
        if self.environment_id:
            self.workspace = self.environment.workspace
        if self.workspace_id:
            self.organization = self.workspace.organization

        if self.is_active and self.user_id and self.pk is None:
            has_default = self.__class__.objects.filter(user=self.user, is_default=True).exists()
            if not has_default:
                self.is_default = True

        return super().save(*args, **kwargs)
