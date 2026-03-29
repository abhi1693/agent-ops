from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import Permission
from django.contrib.auth.models import PermissionsMixin
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone


class UserManager(DjangoUserManager):
    def create_user(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("is_staff", False)
        return self._create_user(username, email, password, **extra_fields)

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_staff", True)
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        return self._create_user(username, email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    username = models.CharField(
        max_length=150,
        unique=True,
        help_text="Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.",
        validators=[UnicodeUsernameValidator()],
        error_messages={"unique": "A user with that username already exists."},
    )
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=150, blank=True)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)
    groups = models.ManyToManyField(
        "users.Group",
        blank=True,
        related_name="users",
        related_query_name="user",
    )
    user_permissions = models.ManyToManyField(
        Permission,
        blank=True,
        related_name="user_set",
        related_query_name="user",
    )
    object_permissions = models.ManyToManyField(
        "users.ObjectPermission",
        blank=True,
        related_name="users",
    )

    objects = UserManager()

    EMAIL_FIELD = "email"
    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]

    class Meta:
        ordering = ("username",)

    def __str__(self) -> str:
        return self.display_name or self.get_full_name() or self.username

    def get_absolute_url(self):
        return reverse("user_detail", args=[self.pk])

    def get_full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self) -> str:
        return self.first_name or self.username

    def get_config(self):
        from .preferences import UserConfig

        config, _created = UserConfig.objects.get_or_create(user=self)
        return config

    def get_active_memberships(self):
        return self.memberships.filter(is_active=True).select_related(
            "organization",
            "workspace",
            "environment",
        )

    def get_default_membership(self):
        memberships = self.get_active_memberships()
        return memberships.filter(is_default=True).first() or memberships.first()

    def clean(self):
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email)
        queryset = self.__class__.objects.exclude(pk=self.pk)

        if queryset.filter(username__iexact=self.username).exists():
            raise ValidationError({"username": "A user with this username already exists."})
        if queryset.filter(email__iexact=self.email).exists():
            raise ValidationError({"email": "A user with this email address already exists."})
        if queryset.filter(email__iexact=self.username).exists():
            raise ValidationError({"username": "This username conflicts with an existing login identifier."})
        if queryset.filter(username__iexact=self.email).exists():
            raise ValidationError({"email": "This email conflicts with an existing login identifier."})
