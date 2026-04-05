from __future__ import annotations

import json
from base64 import urlsafe_b64encode
from hashlib import sha256

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError


def _get_credential_cipher() -> Fernet:
    configured_key = getattr(settings, "AUTOMATION_CREDENTIAL_ENCRYPTION_KEY", None)
    if configured_key is None:
        configured_key = urlsafe_b64encode(sha256(settings.SECRET_KEY.encode("utf-8")).digest()).decode("ascii")

    if not isinstance(configured_key, str) or not configured_key.strip():
        raise ImproperlyConfigured("AUTOMATION_CREDENTIAL_ENCRYPTION_KEY must be a non-empty string.")

    try:
        return Fernet(configured_key.encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured(
            "AUTOMATION_CREDENTIAL_ENCRYPTION_KEY must be a valid Fernet key."
        ) from exc


def encrypt_credential_payload(value: dict[str, object]) -> str:
    if not isinstance(value, dict):
        raise ValidationError({"data": "Credential data must be a JSON object."})

    if not value:
        return ""

    for key in value:
        if not isinstance(key, str) or not key.strip():
            raise ValidationError({"data": "Credential field names must be non-empty strings."})

    serialized = json.dumps(value, separators=(",", ":"), sort_keys=True)
    return _get_credential_cipher().encrypt(serialized.encode("utf-8")).decode("utf-8")


def decrypt_credential_payload(value: str | None) -> dict[str, object]:
    if value in (None, ""):
        return {}

    if not isinstance(value, str):
        raise ValidationError({"data": "Credential data must be stored as text."})

    try:
        decrypted = _get_credential_cipher().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValidationError({"data": "Credential data could not be decrypted."}) from exc

    try:
        parsed = json.loads(decrypted)
    except json.JSONDecodeError as exc:
        raise ValidationError({"data": "Credential data does not contain valid JSON."}) from exc

    if not isinstance(parsed, dict):
        raise ValidationError({"data": "Credential data must decode to a JSON object."})

    normalized: dict[str, object] = {}
    for key, raw_value in parsed.items():
        if not isinstance(key, str) or not key.strip():
            raise ValidationError({"data": "Credential field names must be non-empty strings."})
        normalized[key] = raw_value

    return normalized
