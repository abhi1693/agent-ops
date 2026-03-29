from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import m2m_changed, post_save, pre_delete, pre_save
from django.dispatch import receiver

from .models import ChangeLoggedModel, ObjectChange
from .request_tracking import get_current_request


def _is_change_logged_instance(instance) -> bool:
    return isinstance(instance, ChangeLoggedModel)


def _get_request_user(request):
    if request is None:
        return None

    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return user


def _merge_existing_change(instance, objectchange, request):
    request_id = getattr(request, "id", None)
    if request_id is None:
        return False

    content_type = ContentType.objects.get_for_model(instance, for_concrete_model=False)
    previous_change = ObjectChange.objects.filter(
        changed_object_type=content_type,
        changed_object_id=instance.pk,
        request_id=request_id,
    ).first()
    if previous_change is None:
        return False

    previous_change.postchange_data = objectchange.postchange_data
    previous_change.related_object_type = objectchange.related_object_type
    previous_change.related_object_id = objectchange.related_object_id
    previous_change.save(
        update_fields=(
            "postchange_data",
            "related_object_type",
            "related_object_id",
        )
    )
    return True


def _record_object_change(instance, action, *, allow_merge=False):
    objectchange = instance.to_objectchange(action)
    if objectchange is None or not objectchange.has_changes:
        instance.__dict__.pop("_prechange_snapshot", None)
        return

    request = get_current_request()
    user = _get_request_user(request)
    request_id = getattr(request, "id", None)
    if allow_merge and _merge_existing_change(instance, objectchange, request):
        instance.__dict__.pop("_prechange_snapshot", None)
        return

    objectchange.user = user
    objectchange.user_name = "" if user is None else user.get_username()
    objectchange.request_id = request_id
    objectchange.save()
    instance.__dict__.pop("_prechange_snapshot", None)


@receiver(pre_save)
def snapshot_prechange_state(sender, instance, **kwargs):
    if not issubclass(sender, ChangeLoggedModel):
        return
    if instance.pk is None:
        return
    if getattr(instance, "_prechange_snapshot", None) is not None:
        return

    try:
        original = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    instance._prechange_snapshot = original.serialize_object()


@receiver(post_save)
def record_saved_object_change(sender, instance, created, **kwargs):
    if not issubclass(sender, ChangeLoggedModel):
        return

    action = ObjectChange.ActionChoices.CREATE if created else ObjectChange.ActionChoices.UPDATE
    _record_object_change(instance, action, allow_merge=not created)


@receiver(pre_delete)
def record_deleted_object_change(sender, instance, **kwargs):
    if not issubclass(sender, ChangeLoggedModel):
        return

    instance.snapshot()
    _record_object_change(instance, ObjectChange.ActionChoices.DELETE)


@receiver(m2m_changed)
def record_m2m_object_change(sender, instance, action, reverse, **kwargs):
    if reverse or not _is_change_logged_instance(instance):
        return

    if action in {"pre_add", "pre_remove", "pre_clear"}:
        if getattr(instance, "_prechange_snapshot", None) is None:
            instance.snapshot()
        return

    if action not in {"post_add", "post_remove", "post_clear"}:
        return

    _record_object_change(instance, ObjectChange.ActionChoices.UPDATE, allow_merge=True)
