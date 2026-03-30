from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse

from core.models import ChangeLoggedModel, PrimaryModel
from integrations.secrets import get_secrets_provider


def _derive_scope_from_environment(workspace, environment):
    if environment is not None and workspace is None:
        workspace = environment.workspace
    return workspace


def _derive_scope_from_workspace(organization, workspace):
    if workspace is not None and organization is None:
        organization = workspace.organization
    return organization


def _derive_scope(*, organization, workspace, environment):
    workspace = _derive_scope_from_environment(workspace, environment)
    organization = _derive_scope_from_workspace(organization, workspace)
    return organization, workspace, environment


def _validate_scope_consistency(*, organization, workspace, environment):
    if workspace is not None and organization is not None and workspace.organization_id != organization.pk:
        raise ValidationError(
            {
                "organization": "Organization must match the selected workspace.",
                "workspace": "Workspace belongs to a different organization.",
            }
        )

    if environment is None:
        return

    expected_workspace = environment.workspace
    expected_organization = expected_workspace.organization

    if workspace is not None and workspace.pk != expected_workspace.pk:
        raise ValidationError(
            {
                "workspace": "Workspace must match the selected environment.",
                "environment": "Environment belongs to a different workspace.",
            }
        )

    if organization is not None and organization.pk != expected_organization.pk:
        raise ValidationError(
            {
                "organization": "Organization must match the selected environment.",
                "environment": "Environment belongs to a different organization.",
            }
        )


def _get_scope_related_object(*, organization, workspace, environment):
    if environment is not None:
        return environment
    if workspace is not None:
        return workspace
    return organization


def _validate_unique_scope_name(instance, *, queryset, message):
    duplicate_qs = queryset.exclude(pk=instance.pk).filter(
        organization=instance.organization,
        workspace=instance.workspace,
        environment=instance.environment,
        name=instance.name,
    )
    if duplicate_qs.exists():
        raise ValidationError({"name": message})


def _validate_json_object(value, *, field_name):
    if not isinstance(value, dict):
        raise ValidationError({field_name: "This field must be a JSON object."})


class Secret(PrimaryModel):
    provider = models.SlugField(
        max_length=100,
        help_text="Registered secrets backend provider slug.",
    )
    organization = models.ForeignKey(
        "tenancy.Organization",
        on_delete=models.CASCADE,
        related_name="secrets",
        blank=True,
        null=True,
    )
    workspace = models.ForeignKey(
        "tenancy.Workspace",
        on_delete=models.CASCADE,
        related_name="secrets",
        blank=True,
        null=True,
    )
    environment = models.ForeignKey(
        "tenancy.Environment",
        on_delete=models.CASCADE,
        related_name="secrets",
        blank=True,
        null=True,
    )
    name = models.CharField(max_length=100)
    parameters = models.JSONField(
        default=dict,
        blank=True,
        help_text="Provider-specific retrieval parameters, not the secret value itself.",
    )
    enabled = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    last_verified = models.DateTimeField(blank=True, null=True)
    last_rotated = models.DateTimeField(blank=True, null=True)
    expires = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("organization__name", "workspace__name", "environment__name", "name")
        constraints = (
            models.UniqueConstraint(
                fields=("environment", "provider", "name"),
                condition=models.Q(environment__isnull=False),
                name="integrations_secret_unique_environment_provider_name",
            ),
            models.UniqueConstraint(
                fields=("workspace", "provider", "name"),
                condition=models.Q(workspace__isnull=False, environment__isnull=True),
                name="integrations_secret_unique_workspace_provider_name",
            ),
            models.UniqueConstraint(
                fields=("organization", "provider", "name"),
                condition=models.Q(workspace__isnull=True, environment__isnull=True),
                name="integrations_secret_unique_organization_provider_name",
            ),
        )

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self):
        return reverse("secret_detail", args=[self.pk])

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

    def get_provider_display(self) -> str:
        provider = get_secrets_provider(self.provider)
        if provider is None:
            return self.provider
        return provider.name or provider.slug

    def get_value(self, obj=None, **kwargs):
        provider = get_secrets_provider(self.provider)
        if provider is None:
            raise ValidationError({"provider": f'No registered provider "{self.provider}" is available.'})
        return provider.get_value_for_secret(self, obj=obj, **kwargs)

    def clean(self):
        super().clean()

        self.organization, self.workspace, self.environment = _derive_scope(
            organization=self.organization,
            workspace=self.workspace,
            environment=self.environment,
        )
        _validate_scope_consistency(
            organization=self.organization,
            workspace=self.workspace,
            environment=self.environment,
        )
        _validate_json_object(self.parameters, field_name="parameters")
        _validate_json_object(self.metadata, field_name="metadata")

        provider = get_secrets_provider(self.provider)
        if provider is None:
            raise ValidationError({"provider": f'No registered provider "{self.provider}" is available.'})
        provider.validate_parameters(self.parameters)

        if self.organization is None:
            raise ValidationError({"organization": "A secret must be scoped to at least an organization."})

        _validate_unique_scope_name(
            self,
            queryset=self.__class__.objects.filter(provider=self.provider),
            message="A secret with this provider and name already exists for the selected scope.",
        )

    def save(self, *args, **kwargs):
        self.organization, self.workspace, self.environment = _derive_scope(
            organization=self.organization,
            workspace=self.workspace,
            environment=self.environment,
        )
        return super().save(*args, **kwargs)

    def get_changelog_related_object(self):
        return _get_scope_related_object(
            organization=self.organization,
            workspace=self.workspace,
            environment=self.environment,
        )


class SecretGroup(PrimaryModel):
    organization = models.ForeignKey(
        "tenancy.Organization",
        on_delete=models.CASCADE,
        related_name="secret_groups",
        blank=True,
        null=True,
    )
    workspace = models.ForeignKey(
        "tenancy.Workspace",
        on_delete=models.CASCADE,
        related_name="secret_groups",
        blank=True,
        null=True,
    )
    environment = models.ForeignKey(
        "tenancy.Environment",
        on_delete=models.CASCADE,
        related_name="secret_groups",
        blank=True,
        null=True,
    )
    name = models.CharField(max_length=100)
    secrets = models.ManyToManyField(
        "integrations.Secret",
        through="integrations.SecretGroupAssignment",
        related_name="secret_groups",
        blank=True,
    )

    class Meta:
        ordering = ("organization__name", "workspace__name", "environment__name", "name")
        constraints = (
            models.UniqueConstraint(
                fields=("environment", "name"),
                condition=models.Q(environment__isnull=False),
                name="integrations_secretgroup_unique_environment_name",
            ),
            models.UniqueConstraint(
                fields=("workspace", "name"),
                condition=models.Q(workspace__isnull=False, environment__isnull=True),
                name="integrations_secretgroup_unique_workspace_name",
            ),
            models.UniqueConstraint(
                fields=("organization", "name"),
                condition=models.Q(workspace__isnull=True, environment__isnull=True),
                name="integrations_secretgroup_unique_organization_name",
            ),
        )

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self):
        return reverse("secretgroup_detail", args=[self.pk])

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

        self.organization, self.workspace, self.environment = _derive_scope(
            organization=self.organization,
            workspace=self.workspace,
            environment=self.environment,
        )
        _validate_scope_consistency(
            organization=self.organization,
            workspace=self.workspace,
            environment=self.environment,
        )

        if self.organization is None:
            raise ValidationError({"organization": "A secret group must be scoped to at least an organization."})

        _validate_unique_scope_name(
            self,
            queryset=self.__class__.objects.all(),
            message="A secret group with this name already exists for the selected scope.",
        )

    def save(self, *args, **kwargs):
        self.organization, self.workspace, self.environment = _derive_scope(
            organization=self.organization,
            workspace=self.workspace,
            environment=self.environment,
        )
        return super().save(*args, **kwargs)

    def get_changelog_related_object(self):
        return _get_scope_related_object(
            organization=self.organization,
            workspace=self.workspace,
            environment=self.environment,
        )


class SecretGroupAssignment(ChangeLoggedModel):
    secret_group = models.ForeignKey(
        "integrations.SecretGroup",
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    secret = models.ForeignKey(
        "integrations.Secret",
        on_delete=models.CASCADE,
        related_name="group_assignments",
    )
    organization = models.ForeignKey(
        "tenancy.Organization",
        on_delete=models.CASCADE,
        related_name="secret_group_assignments",
        blank=True,
        null=True,
    )
    workspace = models.ForeignKey(
        "tenancy.Workspace",
        on_delete=models.CASCADE,
        related_name="secret_group_assignments",
        blank=True,
        null=True,
    )
    environment = models.ForeignKey(
        "tenancy.Environment",
        on_delete=models.CASCADE,
        related_name="secret_group_assignments",
        blank=True,
        null=True,
    )
    key = models.SlugField(
        max_length=100,
        help_text="Stable role or key for this secret within the group.",
    )
    required = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=100)

    class Meta:
        ordering = (
            "organization__name",
            "workspace__name",
            "environment__name",
            "secret_group__name",
            "order",
            "key",
        )
        constraints = (
            models.UniqueConstraint(
                fields=("secret_group", "key"),
                name="integrations_secretgroupassignment_unique_group_key",
            ),
            models.UniqueConstraint(
                fields=("secret_group", "secret"),
                name="integrations_secretgroupassignment_unique_group_secret",
            ),
        )

    def __str__(self) -> str:
        return f"{self.secret_group} / {self.key}"

    def get_absolute_url(self):
        return reverse("secretgroupassignment_detail", args=[self.pk])

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

        if self.secret_group_id:
            self.organization = self.secret_group.organization
            self.workspace = self.secret_group.workspace
            self.environment = self.secret_group.environment

        if not self.secret_group_id or not self.secret_id:
            return

        if self.secret.organization_id != self.secret_group.organization_id:
            raise ValidationError(
                {
                    "secret_group": "Secret group and secret must belong to the same organization.",
                    "secret": "Secret belongs to a different organization.",
                }
            )
        if self.secret.workspace_id != self.secret_group.workspace_id:
            raise ValidationError(
                {
                    "secret_group": "Secret group and secret must use the same workspace scope.",
                    "secret": "Secret belongs to a different workspace scope.",
                }
            )
        if self.secret.environment_id != self.secret_group.environment_id:
            raise ValidationError(
                {
                    "secret_group": "Secret group and secret must use the same environment scope.",
                    "secret": "Secret belongs to a different environment scope.",
                }
            )

    def save(self, *args, **kwargs):
        if self.secret_group_id:
            self.organization = self.secret_group.organization
            self.workspace = self.secret_group.workspace
            self.environment = self.secret_group.environment
        return super().save(*args, **kwargs)

    def get_changelog_related_object(self):
        return self.secret_group
