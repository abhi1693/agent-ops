from django.contrib.auth.models import GroupManager as DjangoGroupManager
from django.contrib.auth.models import Permission
from django.db import models
from django.urls import reverse


class Group(models.Model):
    name = models.CharField(max_length=150, unique=True)
    description = models.CharField(max_length=200, blank=True)
    permissions = models.ManyToManyField(
        Permission,
        blank=True,
        related_name="groups",
        related_query_name="group",
    )
    object_permissions = models.ManyToManyField(
        "users.ObjectPermission",
        blank=True,
        related_name="groups",
    )

    objects = DjangoGroupManager()

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self):
        return reverse("group_detail", args=[self.pk])
