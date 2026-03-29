from __future__ import annotations

import os
from abc import ABC, abstractmethod

from django import forms
from django.core.exceptions import ImproperlyConfigured, ValidationError


_SECRETS_PROVIDERS: dict[str, type["SecretsProvider"]] = {}


class SecretsProvider(ABC):
    slug: str | None = None
    name: str | None = None
    ParametersForm: type[forms.Form] = forms.Form

    @classmethod
    def validate_parameters(cls, parameters: dict) -> None:
        form = cls.ParametersForm(parameters)
        if form.is_valid():
            return

        errors = []
        for field_name, field_errors in form.errors.items():
            label = "non_field_errors" if field_name == "__all__" else field_name
            errors.append(f"{label}: {' '.join(field_errors)}")
        raise ValidationError({"parameters": " ".join(errors)})

    @classmethod
    @abstractmethod
    def get_value_for_secret(cls, secret, obj=None, **kwargs):
        raise NotImplementedError


def register_secrets_provider(provider: type[SecretsProvider]) -> type[SecretsProvider]:
    slug = getattr(provider, "slug", None)
    if not slug:
        raise ImproperlyConfigured("Secrets providers must define a non-empty slug.")

    existing = _SECRETS_PROVIDERS.get(slug)
    if existing is not None and existing is not provider:
        raise ImproperlyConfigured(f'A secrets provider with slug "{slug}" is already registered.')

    _SECRETS_PROVIDERS[slug] = provider
    return provider


def get_secrets_provider(slug: str) -> type[SecretsProvider] | None:
    return _SECRETS_PROVIDERS.get(slug)


def iter_secrets_providers():
    return _SECRETS_PROVIDERS.items()


@register_secrets_provider
class EnvironmentVariableSecretsProvider(SecretsProvider):
    slug = "environment-variable"
    name = "Environment Variable"

    class ParametersForm(forms.Form):
        variable = forms.CharField(max_length=255, required=True)

    @classmethod
    def get_value_for_secret(cls, secret, obj=None, **kwargs):
        variable = secret.parameters["variable"]
        try:
            return os.environ[variable]
        except KeyError as exc:
            raise ValidationError({"parameters": f'Environment variable "{variable}" is not set.'}) from exc
