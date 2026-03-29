from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ("username",)

    def __str__(self) -> str:
        return self.display_name or self.username
