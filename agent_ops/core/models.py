import json

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models


__all__ = (
    "BaseModel",
    "ChangeLoggedModel",
    "ObjectChange",
    "OrganizationalModel",
    "PrimaryModel",
)


class BaseModel(models.Model):
    """
    Global abstract base model for application objects.
    """

    class Meta:
        abstract = True


class ChangeLoggedModel(BaseModel):
    """
    Base model for ancillary objects.

    This mirrors the shared model hierarchy entry point for models that do not need
    the richer "primary" or "organizational" semantics.
    """

    created = models.DateTimeField(
        auto_now_add=True,
        blank=True,
        null=True,
    )
    last_updated = models.DateTimeField(
        auto_now=True,
        blank=True,
        null=True,
    )

    changelog_exclude_fields = ()

    class Meta:
        abstract = True

    def get_changelog_exclude_fields(self) -> set[str]:
        return {
            "created",
            "last_updated",
            *self.changelog_exclude_fields,
        }

    def get_changelog_related_object(self):
        return None

    def _serialize_value(self, value):
        return json.loads(json.dumps(value, cls=DjangoJSONEncoder))

    def serialize_object(self, exclude=None):
        excluded_fields = self.get_changelog_exclude_fields()
        if exclude:
            excluded_fields.update(exclude)

        data = {}
        for field in self._meta.concrete_fields:
            if field.name in excluded_fields:
                continue
            data[field.name] = self._serialize_value(field.value_from_object(self))

        for field in self._meta.local_many_to_many:
            if field.name in excluded_fields:
                continue
            if self.pk is None:
                data[field.name] = []
                continue
            values = list(getattr(self, field.name).order_by("pk").values_list("pk", flat=True))
            data[field.name] = self._serialize_value(values)

        return data

    def snapshot(self):
        self._prechange_snapshot = self.serialize_object()

    snapshot.alters_data = True

    def to_objectchange(self, action):
        related_object = self.get_changelog_related_object()
        objectchange = ObjectChange(
            action=action,
            changed_object=self,
            related_object=related_object,
            object_repr=str(self)[:200],
        )

        if hasattr(self, "_prechange_snapshot"):
            objectchange.prechange_data = self._prechange_snapshot

        if action in {ObjectChange.ActionChoices.CREATE, ObjectChange.ActionChoices.UPDATE}:
            objectchange.postchange_data = self.serialize_object()

        return objectchange


class PrimaryModel(ChangeLoggedModel):
    """
    Base model for primary managed objects.
    """

    description = models.CharField(max_length=200, blank=True)

    class Meta:
        abstract = True


class ObjectChange(models.Model):
    class ActionChoices(models.TextChoices):
        CREATE = "create", "Create"
        UPDATE = "update", "Update"
        DELETE = "delete", "Delete"

    action_badge_classes = {
        ActionChoices.CREATE: "text-bg-success",
        ActionChoices.UPDATE: "text-bg-primary",
        ActionChoices.DELETE: "text-bg-danger",
    }

    time = models.DateTimeField(auto_now_add=True, editable=False, db_index=True)
    user = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="changes",
        blank=True,
        null=True,
    )
    user_name = models.CharField(max_length=150, editable=False, blank=True)
    request_id = models.UUIDField(editable=False, db_index=True, blank=True, null=True)
    action = models.CharField(max_length=20, choices=ActionChoices.choices)
    changed_object_type = models.ForeignKey(
        to="contenttypes.ContentType",
        on_delete=models.PROTECT,
        related_name="+",
    )
    changed_object_id = models.PositiveBigIntegerField()
    changed_object = GenericForeignKey(
        ct_field="changed_object_type",
        fk_field="changed_object_id",
    )
    related_object_type = models.ForeignKey(
        to="contenttypes.ContentType",
        on_delete=models.PROTECT,
        related_name="+",
        blank=True,
        null=True,
    )
    related_object_id = models.PositiveBigIntegerField(blank=True, null=True)
    related_object = GenericForeignKey(
        ct_field="related_object_type",
        fk_field="related_object_id",
    )
    object_repr = models.CharField(max_length=200, editable=False)
    prechange_data = models.JSONField(editable=False, blank=True, null=True)
    postchange_data = models.JSONField(editable=False, blank=True, null=True)

    class Meta:
        ordering = ("-time",)
        indexes = (
            models.Index(fields=("changed_object_type", "changed_object_id")),
            models.Index(fields=("related_object_type", "related_object_id")),
        )

    def __str__(self):
        action = self.get_action_display().lower()
        return f"{self.object_repr} {action}"

    def save(self, *args, **kwargs):
        if not self.user_name and self.user is not None:
            self.user_name = self.user.get_username()
        if not self.object_repr and self.changed_object is not None:
            self.object_repr = str(self.changed_object)[:200]
        return super().save(*args, **kwargs)

    @property
    def has_changes(self) -> bool:
        return self.prechange_data != self.postchange_data

    @property
    def badge_class(self) -> str:
        return self.action_badge_classes.get(self.action, "text-bg-secondary")

    @property
    def diff_items(self):
        prechange = self.prechange_data or {}
        postchange = self.postchange_data or {}

        if self.action == self.ActionChoices.CREATE:
            changed_keys = sorted(postchange)
        elif self.action == self.ActionChoices.DELETE:
            changed_keys = sorted(prechange)
        else:
            changed_keys = sorted(
                key for key in {*prechange, *postchange} if prechange.get(key) != postchange.get(key)
            )

        return [
            {
                "field": key,
                "before": prechange.get(key),
                "after": postchange.get(key),
            }
            for key in changed_keys
        ]


class OrganizationalModel(ChangeLoggedModel):
    """
    Base model for naming/categorization objects.
    """

    name = models.CharField(max_length=150, unique=True)
    description = models.CharField(max_length=200, blank=True)

    class Meta:
        abstract = True
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name
