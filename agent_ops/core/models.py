from django.db import models


__all__ = (
    "BaseModel",
    "ChangeLoggedModel",
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

    class Meta:
        abstract = True


class PrimaryModel(ChangeLoggedModel):
    """
    Base model for primary managed objects.
    """

    description = models.CharField(max_length=200, blank=True)

    class Meta:
        abstract = True


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
