from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import PermissionDenied

from users.models import Group, Membership, ObjectPermission


ACTIVE_MEMBERSHIP_SESSION_KEY = "users.active_membership_id"
ACTIVE_MEMBERSHIP_HEADER = "X-AgentOps-Membership"
ACTIVE_MEMBERSHIP_QUERY_PARAM = "membership"


@dataclass(frozen=True)
class ActorScope:
    user: object
    membership: Membership | None = None
    organization: object | None = None
    workspace: object | None = None
    environment: object | None = None

    @property
    def is_staff(self) -> bool:
        return bool(self.user and (self.user.is_staff or self.user.is_superuser))

    @property
    def is_scoped(self) -> bool:
        return self.membership is not None


def get_membership_queryset(user):
    return user.memberships.filter(is_active=True).select_related(
        "organization",
        "workspace",
        "environment",
    ).prefetch_related(
        "groups",
        "groups__permissions",
        "groups__object_permissions",
        "object_permissions",
    )


def set_active_membership(request, membership: Membership | None) -> None:
    if membership is None:
        request.session.pop(ACTIVE_MEMBERSHIP_SESSION_KEY, None)
    else:
        request.session[ACTIVE_MEMBERSHIP_SESSION_KEY] = membership.pk


def _build_actor_scope(user, membership: Membership | None) -> ActorScope:
    if membership is None:
        return ActorScope(user=user)
    return ActorScope(
        user=user,
        membership=membership,
        organization=membership.organization,
        workspace=membership.workspace,
        environment=membership.environment,
    )


def _get_explicit_membership_id(request):
    header_value = request.headers.get(ACTIVE_MEMBERSHIP_HEADER)
    if header_value:
        return header_value
    return request.GET.get(ACTIVE_MEMBERSHIP_QUERY_PARAM)


def _parse_membership_id(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise PermissionDenied("Membership selector must be an integer.") from exc


def resolve_actor_scope(request) -> ActorScope | None:
    user = request.user
    if not user or not user.is_authenticated:
        return None

    if user.is_staff or user.is_superuser:
        return ActorScope(user=user)

    membership_qs = get_membership_queryset(user)

    token = getattr(request, "auth", None)
    token_membership_id = getattr(token, "scope_membership_id", None)
    if token_membership_id:
        membership = membership_qs.filter(pk=token_membership_id).first()
        if membership is None:
            raise PermissionDenied("Token scope is no longer valid.")
        return _build_actor_scope(user, membership)

    explicit_membership_id = _parse_membership_id(_get_explicit_membership_id(request))
    if explicit_membership_id is not None:
        membership = membership_qs.filter(pk=explicit_membership_id).first()
        if membership is None:
            raise PermissionDenied("Requested membership is not available.")
        return _build_actor_scope(user, membership)

    session_membership_id = _parse_membership_id(
        request.session.get(ACTIVE_MEMBERSHIP_SESSION_KEY)
    ) if hasattr(request, "session") else None
    if session_membership_id is not None:
        membership = membership_qs.filter(pk=session_membership_id).first()
        if membership is not None:
            return _build_actor_scope(user, membership)
        request.session.pop(ACTIVE_MEMBERSHIP_SESSION_KEY, None)

    membership = user.get_default_membership()
    return _build_actor_scope(user, membership) if membership else None


def get_request_actor_scope(request) -> ActorScope | None:
    if not hasattr(request, "_agent_ops_actor_scope_resolved"):
        request.actor_scope = resolve_actor_scope(request)
        request._agent_ops_actor_scope_resolved = True
    return getattr(request, "actor_scope", None)


def get_effective_groups(user, membership: Membership | None = None):
    group_ids = set(user.groups.values_list("pk", flat=True))
    if membership is not None:
        group_ids.update(membership.groups.values_list("pk", flat=True))
    if not group_ids:
        return Group.objects.none()
    return Group.objects.filter(pk__in=group_ids).order_by("name")


def get_effective_object_permissions(user, membership: Membership | None = None):
    permission_ids = set(user.object_permissions.values_list("pk", flat=True))
    permission_ids.update(
        user.groups.values_list("object_permissions__pk", flat=True)
    )
    if membership is not None:
        permission_ids.update(membership.object_permissions.values_list("pk", flat=True))
        permission_ids.update(
            membership.groups.values_list("object_permissions__pk", flat=True)
        )

    permission_ids.discard(None)
    if not permission_ids:
        return ObjectPermission.objects.none()

    return ObjectPermission.objects.filter(
        pk__in=permission_ids,
        enabled=True,
    ).prefetch_related("content_types").distinct().order_by("name")
