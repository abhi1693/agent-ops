from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import transaction

from users.restrictions import (
    assert_object_action_allowed,
    has_model_action_permission,
    is_object_action_allowed,
    restrict_queryset,
)


class RestrictedModelPermissionMixin(LoginRequiredMixin, UserPassesTestMixin):
    raise_exception = True
    permission_action = "view"

    def get_permission_action(self):
        return self.permission_action

    def get_permission_model(self):
        queryset = getattr(self, "queryset", None)
        if queryset is not None:
            return queryset.model
        if getattr(self, "model", None) is not None:
            return self.model
        return self.get_queryset().model

    def test_func(self):
        return has_model_action_permission(
            self.get_permission_model(),
            request=self.request,
            action=self.get_permission_action(),
        )


class RestrictedObjectListMixin(RestrictedModelPermissionMixin):
    permission_action = "view"

    def get_queryset(self, request):
        return restrict_queryset(
            super().get_queryset(request),
            request=request,
            action=self.get_permission_action(),
        )

    def get_extra_context(self, request):
        context = super().get_extra_context(request)
        context["can_add"] = has_model_action_permission(
            self.get_permission_model(),
            request=request,
            action="add",
        )
        return context


class RestrictedObjectViewMixin(RestrictedModelPermissionMixin):
    permission_action = "view"

    def get_queryset(self):
        return restrict_queryset(
            super().get_queryset(),
            request=self.request,
            action=self.get_permission_action(),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["can_edit"] = is_object_action_allowed(
            self.object,
            request=self.request,
            action="change",
        )
        return context


class RestrictedObjectChangeLogMixin(RestrictedModelPermissionMixin):
    permission_action = "view"

    def get_queryset(self):
        return restrict_queryset(
            super().get_queryset(),
            request=self.request,
            action=self.get_permission_action(),
        )

    def get_extra_context(self, request, obj=None):
        context = super().get_extra_context(request, obj)
        if obj is not None:
            context["can_edit"] = is_object_action_allowed(
                obj,
                request=request,
                action="change",
            )
        return context


class RestrictedObjectEditMixin(RestrictedModelPermissionMixin):
    def get_permission_action(self):
        return "change" if getattr(self, "kwargs", None) else "add"

    def get_queryset(self):
        return restrict_queryset(
            super().get_queryset(),
            request=self.request,
            action=self.get_permission_action(),
        )

    def get_form(self, data=None, files=None):
        return self.get_form_class()(
            data=data,
            files=files,
            instance=self.object,
            request=self.request,
        )

    def form_save(self, form):
        with transaction.atomic():
            obj = super().form_save(form)
            assert_object_action_allowed(
                obj,
                request=self.request,
                action=self.get_permission_action(),
            )
            return obj


class RestrictedObjectDeleteMixin(RestrictedModelPermissionMixin):
    permission_action = "delete"

    def get_queryset(self):
        return restrict_queryset(
            super().get_queryset(),
            request=self.request,
            action=self.get_permission_action(),
        )
