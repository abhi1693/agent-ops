import hashlib
import hmac
import secrets
import string

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.models import PrimaryModel


TOKEN_CHARSET = string.ascii_letters + string.digits
TOKEN_DEFAULT_LENGTH = 40
TOKEN_KEY_LENGTH = 12
TOKEN_PREFIX = "agt_"


class Token(PrimaryModel):
    _token = None
    changelog_exclude_fields = ("digest",)

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="tokens",
    )
    scope_membership = models.ForeignKey(
        "users.Membership",
        on_delete=models.PROTECT,
        related_name="tokens",
        blank=True,
        null=True,
    )
    created = models.DateTimeField(auto_now_add=True)
    expires = models.DateTimeField(blank=True, null=True)
    last_used = models.DateTimeField(blank=True, null=True)
    enabled = models.BooleanField(
        default=True,
        help_text="Disable to revoke this token without deleting it.",
    )
    write_enabled = models.BooleanField(
        default=True,
        help_text="Permit create, update, and delete operations with this token.",
    )
    key = models.CharField(max_length=TOKEN_KEY_LENGTH, unique=True, editable=False)
    digest = models.CharField(max_length=64, unique=True, editable=False)

    class Meta:
        ordering = ("-created",)

    def __str__(self) -> str:
        return self.masked_key

    def get_absolute_url(self):
        return reverse("token_list")

    @property
    def masked_key(self) -> str:
        return f"{TOKEN_PREFIX}{self.key}"

    @property
    def plaintext_token(self):
        if self._token is None:
            return None
        return f"{TOKEN_PREFIX}{self.key}.{self._token}"

    @property
    def is_expired(self) -> bool:
        return self.expires is not None and timezone.now() >= self.expires

    @property
    def is_active(self) -> bool:
        return self.enabled and not self.is_expired

    def clean(self):
        super().clean()
        if self.pk is None and self.expires is not None and self.expires <= timezone.now():
            raise ValidationError({"expires": "Expiration time must be in the future."})
        if self.scope_membership_id and self.user_id and self.scope_membership.user_id != self.user_id:
            raise ValidationError(
                {"scope_membership": "Selected membership must belong to the token owner."}
            )

    def save(self, *args, **kwargs):
        if self._state.adding and self._token is None:
            self.assign_token()
        return super().save(*args, **kwargs)

    def assign_token(self, token=None):
        if not self._state.adding:
            raise ValueError("Cannot assign a new plaintext value for an existing token.")

        self._token = token or self.generate()
        self.key = self.key or self.generate_key()
        self.digest = self.build_digest(self._token)

    def build_digest(self, token: str) -> str:
        return hmac.new(settings.SECRET_KEY.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()

    def validate(self, token: str) -> bool:
        candidate = token.strip()
        prefix = f"{TOKEN_PREFIX}{self.key}."
        if candidate.startswith(prefix):
            candidate = candidate.removeprefix(prefix)
        digest = self.build_digest(candidate)
        return self.is_active and hmac.compare_digest(digest, self.digest)

    @classmethod
    def generate_key(cls) -> str:
        while True:
            key = cls.generate(TOKEN_KEY_LENGTH)
            if not cls.objects.filter(key=key).exists():
                return key

    @staticmethod
    def generate(length=TOKEN_DEFAULT_LENGTH) -> str:
        return "".join(secrets.choice(TOKEN_CHARSET) for _ in range(length))

    def get_changelog_related_object(self):
        return self.user
