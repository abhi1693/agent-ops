from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.urls import NoReverseMatch, reverse

from core.models import ObjectChange
from tenancy.models import Environment, Organization, Workspace
from users.restrictions import resolve_restriction_scope, restrict_queryset


VISIBLE_CHANGE_MODELS = (Organization, Workspace, Environment)


def get_objectchange_target_url(change):
    if change.action != ObjectChange.ActionChoices.DELETE:
        try:
            return reverse(
                f"{change.changed_object_type.model}_changelog",
                args=[change.changed_object_id],
            )
        except NoReverseMatch:
            pass

    if change.related_object_type_id and change.related_object_id:
        try:
            return reverse(
                f"{change.related_object_type.model}_changelog",
                args=[change.related_object_id],
            )
        except NoReverseMatch:
            pass

    return None


def restrict_objectchange_queryset(queryset, *, request=None, actor_scope=None):
    actor_scope = resolve_restriction_scope(request=request, actor_scope=actor_scope)
    if actor_scope is None:
        return queryset.none()
    if actor_scope.is_staff:
        return queryset

    change_filter = Q()
    for model in VISIBLE_CHANGE_MODELS:
        content_type = ContentType.objects.get_for_model(model, for_concrete_model=False)
        visible_ids = list(
            restrict_queryset(
                model.objects.only("pk"),
                actor_scope=actor_scope,
                action="view",
            ).values_list("pk", flat=True)
        )
        if not visible_ids:
            continue

        change_filter |= Q(
            changed_object_type=content_type,
            changed_object_id__in=visible_ids,
        )
        change_filter |= Q(
            related_object_type=content_type,
            related_object_id__in=visible_ids,
        )

    if not change_filter.children:
        return queryset.none()

    return queryset.filter(change_filter).distinct()
