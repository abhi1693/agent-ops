from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse


class ObjectPermission(models.Model):
    class ActionChoices(models.TextChoices):
        VIEW = "view", "View"
        ADD = "add", "Add"
        CHANGE = "change", "Change"
        DELETE = "delete", "Delete"

    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=200, blank=True)
    enabled = models.BooleanField(default=True)
    content_types = models.ManyToManyField("contenttypes.ContentType", related_name="object_permissions")
    actions = models.JSONField(default=list)
    constraints = models.JSONField(blank=True, null=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self):
        return reverse("objectpermission_detail", args=[self.pk])

    def clean(self):
        super().clean()
        valid_actions = {choice for choice, _label in self.ActionChoices.choices}
        if not isinstance(self.actions, list):
            raise ValidationError({"actions": "Actions must be a list."})
        invalid_actions = [action for action in self.actions if action not in valid_actions]
        if invalid_actions:
            raise ValidationError({"actions": f"Invalid actions: {', '.join(invalid_actions)}"})
        if len(set(self.actions)) != len(self.actions):
            raise ValidationError({"actions": "Duplicate actions are not allowed."})
        if self.constraints is not None and not isinstance(self.constraints, (dict, list)):
            raise ValidationError({"constraints": "Constraints must be a JSON object or list."})

    @property
    def can_view(self) -> bool:
        return self.ActionChoices.VIEW in self.actions

    @property
    def can_add(self) -> bool:
        return self.ActionChoices.ADD in self.actions

    @property
    def can_change(self) -> bool:
        return self.ActionChoices.CHANGE in self.actions

    @property
    def can_delete(self) -> bool:
        return self.ActionChoices.DELETE in self.actions

    def list_constraints(self):
        if self.constraints is None:
            return []
        if isinstance(self.constraints, list):
            return self.constraints
        return [self.constraints]
