from django.utils import timezone
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header

from users.models import Token
from users.models.tokens import TOKEN_PREFIX


TOKEN_KEYWORD = b"token"


class TokenAuthentication(BaseAuthentication):
    """
    Authenticate API requests using the existing Token model.
    """

    def authenticate(self, request):
        auth = get_authorization_header(request).split()
        if not auth:
            return None

        if auth[0].lower() != TOKEN_KEYWORD:
            return None

        if len(auth) != 2:
            raise exceptions.AuthenticationFailed(
                f'Invalid authorization header: expected "Token {TOKEN_PREFIX}<key>.<token>"'
            )

        try:
            value = auth[1].decode()
        except UnicodeError as exc:
            raise exceptions.AuthenticationFailed(
                "Invalid authorization header: token contains invalid characters."
            ) from exc

        if not value.startswith(TOKEN_PREFIX):
            raise exceptions.AuthenticationFailed(
                f'Invalid authorization header: expected "{TOKEN_PREFIX}<key>.<token>".'
            )

        try:
            key, _token = value.removeprefix(TOKEN_PREFIX).split(".", 1)
        except ValueError as exc:
            raise exceptions.AuthenticationFailed(
                f'Invalid authorization header: expected "{TOKEN_PREFIX}<key>.<token>".'
            ) from exc

        try:
            token = Token.objects.select_related(
                "user",
                "scope_membership__organization",
                "scope_membership__workspace",
                "scope_membership__environment",
            ).get(key=key)
        except Token.DoesNotExist as exc:
            raise exceptions.AuthenticationFailed("Invalid token.") from exc

        if not token.validate(value):
            raise exceptions.AuthenticationFailed("Invalid token.")
        if not token.enabled:
            raise exceptions.AuthenticationFailed("Token disabled.")
        if token.is_expired:
            raise exceptions.AuthenticationFailed("Token expired.")
        if not token.user.is_active:
            raise exceptions.AuthenticationFailed("User inactive.")

        now = timezone.now()
        if token.last_used is None or (now - token.last_used).total_seconds() > 60:
            Token.objects.filter(pk=token.pk).update(last_used=now)
            token.last_used = now

        return token.user, token


class TokenAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "agent_ops.api.authentication.TokenAuthentication"
    name = "tokenAuth"
    match_subclasses = True

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "header",
            "name": "Authorization",
            "description": f"`Token {TOKEN_PREFIX}<key>.<token>`",
        }
