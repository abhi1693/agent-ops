from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import FieldDoesNotExist, PermissionDenied
from django.db.models import Q

from users.scopes import ActorScope, get_effective_object_permissions, get_request_actor_scope


CONSTRAINT_TOKEN_USER = "$user"
CONSTRAINT_TOKEN_MEMBERSHIP = "$membership"
CONSTRAINT_TOKEN_ORGANIZATION = "$organization"
CONSTRAINT_TOKEN_WORKSPACE = "$workspace"
CONSTRAINT_TOKEN_ENVIRONMENT = "$environment"


ACTION_BY_METHOD = {
    "GET": "view",
    "HEAD": "view",
    "OPTIONS": "view",
    "POST": "add",
    "PUT": "change",
    "PATCH": "change",
    "DELETE": "delete",
}

IMPLIED_ACTIONS = {
    "view": {"view", "change", "delete"},
    "add": {"add"},
    "change": {"change"},
    "delete": {"delete"},
}


def get_action_for_method(method: str) -> str:
    return ACTION_BY_METHOD.get(method.upper(), "view")


def resolve_restriction_scope(request=None, actor_scope=None):
    if actor_scope is not None:
        return actor_scope
    if request is None:
        return None

    actor_scope = get_request_actor_scope(request)
    if actor_scope is not None:
        return actor_scope

    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        return ActorScope(user=user)

    return None


def _replace_constraint_tokens(value, tokens):
    if isinstance(value, list):
        return [_replace_constraint_tokens(item, tokens) for item in value]
    if isinstance(value, dict):
        return {key: _replace_constraint_tokens(item, tokens) for key, item in value.items()}
    return tokens.get(value, value)


def build_constraint_filter(constraints, tokens=None):
    if not constraints:
        return None

    tokens = tokens or {}
    params = Q()

    for constraint in constraints:
        if constraint in (None, {}):
            return Q()

        params |= Q(
            **{
                key: _replace_constraint_tokens(value, tokens)
                for key, value in constraint.items()
            }
        )

    return params


def _model_has_field(model, field_name: str) -> bool:
    try:
        model._meta.get_field(field_name)
    except FieldDoesNotExist:
        return False
    return True


def _get_scope_constraints(model, actor_scope):
    if actor_scope is None or actor_scope.membership is None:
        return []

    scope_map = (
        ("environment", actor_scope.environment),
        ("workspace", actor_scope.workspace),
        ("organization", actor_scope.organization),
    )

    for field_name, scope_object in scope_map:
        if scope_object is None:
            continue
        if model._meta.concrete_model == scope_object._meta.concrete_model:
            return [{"pk": scope_object.pk}]
        if _model_has_field(model, field_name):
            return [{field_name: scope_object.pk}]

    return []


def _get_constraint_tokens(actor_scope):
    if actor_scope is None:
        return {}

    return {
        CONSTRAINT_TOKEN_USER: actor_scope.user.pk,
        CONSTRAINT_TOKEN_MEMBERSHIP: getattr(actor_scope.membership, "pk", None),
        CONSTRAINT_TOKEN_ORGANIZATION: getattr(actor_scope.organization, "pk", None),
        CONSTRAINT_TOKEN_WORKSPACE: getattr(actor_scope.workspace, "pk", None),
        CONSTRAINT_TOKEN_ENVIRONMENT: getattr(actor_scope.environment, "pk", None),
    }


def _get_permission_constraints(permission):
    if permission.constraints in (None, []):
        return [None]
    if isinstance(permission.constraints, list):
        return permission.constraints
    return [permission.constraints]


def get_matching_object_permissions(model, actor_scope, action: str):
    if actor_scope is None or actor_scope.user is None:
        return []

    content_type = ContentType.objects.get_for_model(model)
    membership = getattr(actor_scope, "membership", None)
    allowed_actions = IMPLIED_ACTIONS[action]
    permissions = get_effective_object_permissions(
        actor_scope.user,
        membership,
    ).filter(
        content_types=content_type,
    ).distinct()

    return [
        permission
        for permission in permissions
        if allowed_actions.intersection(permission.actions)
    ]


def has_model_action_permission(model, request=None, actor_scope=None, action="view") -> bool:
    actor_scope = resolve_restriction_scope(request=request, actor_scope=actor_scope)
    if actor_scope is None:
        return False
    if actor_scope.is_staff:
        return True
    if action == "view" and _get_scope_constraints(model, actor_scope):
        return True
    return bool(get_matching_object_permissions(model, actor_scope, action))


def restrict_queryset(queryset, request=None, actor_scope=None, action="view"):
    actor_scope = resolve_restriction_scope(request=request, actor_scope=actor_scope)
    if actor_scope is None:
        return queryset.none()
    if actor_scope.is_staff:
        return queryset

    model = queryset.model._meta.concrete_model
    constraints = []

    if action == "view":
        constraints.extend(_get_scope_constraints(model, actor_scope))

    for permission in get_matching_object_permissions(model, actor_scope, action):
        constraints.extend(_get_permission_constraints(permission))

    permission_filter = build_constraint_filter(
        constraints,
        tokens=_get_constraint_tokens(actor_scope),
    )
    if permission_filter is None:
        return queryset.none()
    if not permission_filter.children:
        return queryset

    allowed_objects = model._default_manager.filter(permission_filter).values("pk")
    return queryset.filter(pk__in=allowed_objects)


def is_object_action_allowed(instance, request=None, actor_scope=None, action="view") -> bool:
    actor_scope = resolve_restriction_scope(request=request, actor_scope=actor_scope)
    if actor_scope is None:
        return False
    if actor_scope.is_staff:
        return True

    queryset = instance.__class__._default_manager.filter(pk=instance.pk)
    return restrict_queryset(
        queryset,
        actor_scope=actor_scope,
        action=action,
    ).exists()


def assert_object_action_allowed(instance, request=None, actor_scope=None, action="view") -> None:
    if not is_object_action_allowed(
        instance,
        request=request,
        actor_scope=actor_scope,
        action=action,
    ):
        raise PermissionDenied(
            f"You do not have permission to {action} this {instance._meta.verbose_name}."
        )
