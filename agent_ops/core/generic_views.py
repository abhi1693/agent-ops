from collections import Counter

from django.contrib import messages
from django.core.exceptions import ImproperlyConfigured
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.views.generic import DetailView, View

from core.form_widgets import apply_standard_widget_classes


__all__ = (
    "BaseMultiObjectView",
    "ObjectDeleteView",
    "ObjectEditView",
    "ObjectView",
    "ObjectListView",
    "TableMixin",
)


class BaseMultiObjectView(View):
    queryset = None
    table = None
    template_name = None

    def dispatch(self, request, *args, **kwargs):
        self.queryset = self.get_queryset(request)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self, request):
        if self.queryset is None:
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} does not define a queryset. "
                "Set queryset on the class or override get_queryset()."
            )

        return self.queryset.all()

    def get_extra_context(self, request):
        return {}


class TableMixin:
    def get_table(self, data, request):
        if self.table is None:
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} does not define a table class."
            )

        table = self.table(data)
        table.configure(request)
        return table


class QuerysetBackedObjectView(View):
    queryset = None
    model = None

    def get_queryset(self):
        if self.queryset is not None:
            return self.queryset.all()
        if self.model is not None:
            return self.model.objects.all()
        raise ImproperlyConfigured(
            f"{self.__class__.__name__} must define a queryset or model."
        )

    def get_object(self, **kwargs):
        queryset = self.get_queryset()
        if not kwargs:
            return queryset.model()
        return get_object_or_404(queryset, **kwargs)

    def get_list_url(self, obj=None):
        model = (obj or self.get_queryset().model)
        try:
            return reverse(f"{model._meta.model_name}_list")
        except NoReverseMatch:
            return None

    def get_changelog_url(self, obj=None):
        model = obj or self.get_queryset().model
        object_pk = getattr(obj, "pk", None)
        if object_pk is None:
            return None

        try:
            return reverse(f"{model._meta.model_name}_changelog", args=[object_pk])
        except NoReverseMatch:
            return None

    def get_delete_url(self, obj=None):
        model = obj or self.get_queryset().model
        object_pk = getattr(obj, "pk", None)
        if object_pk is None:
            return None

        try:
            return reverse(f"{model._meta.model_name}_delete", args=[object_pk])
        except NoReverseMatch:
            return None

    def get_object_identifier(self, obj):
        return f"{obj._meta.app_label}.{obj._meta.model_name}:{obj.pk}"

    def build_object_context(self, obj):
        meta = obj._meta
        return {
            "object": obj,
            "object_identifier": self.get_object_identifier(obj),
            "object_list_url": self.get_list_url(obj),
            "object_changelog_url": self.get_changelog_url(obj),
            "object_delete_url": self.get_delete_url(obj),
            "object_verbose_name": str(meta.verbose_name).title(),
            "object_verbose_name_plural": str(meta.verbose_name_plural).title(),
        }

    def get_return_url(self, request, obj=None):
        explicit_return_url = request.POST.get("return_url") or request.GET.get("return_url")
        if explicit_return_url and explicit_return_url.startswith("/"):
            return explicit_return_url

        if obj is not None and getattr(obj, "pk", None) and hasattr(obj, "get_absolute_url"):
            return obj.get_absolute_url()

        return self.get_list_url(obj=obj)

    def get_extra_context(self, request, obj=None):
        return {}


class ObjectView(DetailView):
    def get_list_url(self):
        try:
            return reverse(f"{self.object._meta.model_name}_list")
        except NoReverseMatch:
            return None

    def get_delete_url(self):
        try:
            return reverse(f"{self.object._meta.model_name}_delete", args=[self.object.pk])
        except NoReverseMatch:
            return None

    def get_object_identifier(self):
        return f"{self.object._meta.app_label}.{self.object._meta.model_name}:{self.object.pk}"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "active_tab": "view",
                "object_identifier": self.get_object_identifier(),
                "object_list_url": self.get_list_url(),
                "object_changelog_url": self.get_changelog_url(),
                "object_delete_url": self.get_delete_url(),
                "object_verbose_name": str(self.object._meta.verbose_name).title(),
                "object_verbose_name_plural": str(self.object._meta.verbose_name_plural).title(),
                "can_delete": self.get_delete_url() is not None,
            }
        )
        return context

    def get_changelog_url(self):
        try:
            return reverse(f"{self.object._meta.model_name}_changelog", args=[self.object.pk])
        except NoReverseMatch:
            return None


class ObjectEditView(QuerysetBackedObjectView):
    template_name = "users/model_form.html"
    form_class = None
    page_title = None
    submit_label = None
    success_message = None
    show_add_another = True

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object(**kwargs)
        self.object = self.alter_object(self.object, request, args, kwargs)
        return super().dispatch(request, *args, **kwargs)

    def alter_object(self, obj, request, url_args, url_kwargs):
        return obj

    def is_editing(self):
        return bool(self.object.pk)

    def get_form_class(self):
        if self.form_class is None:
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} must define form_class."
            )
        return self.form_class

    def get_form(self, data=None, files=None):
        return self.get_form_class()(data=data, files=files, instance=self.object)

    def get_page_title(self):
        if self.page_title:
            return self.page_title

        meta = self.get_queryset().model._meta
        if self.is_editing():
            return f"Edit {meta.verbose_name}: {self.object}"
        return f"Add {meta.verbose_name}"

    def get_submit_label(self):
        if self.submit_label:
            return self.submit_label
        return "Save" if self.is_editing() else "Create"

    def get_addanother_url(self):
        try:
            return reverse(f"{self.get_queryset().model._meta.model_name}_add")
        except NoReverseMatch:
            return None

    def get_show_add_another(self):
        return not self.is_editing() and self.show_add_another and self.get_addanother_url() is not None

    def get_success_message(self, obj, created):
        if self.success_message:
            return self.success_message
        action = "Created" if created else "Updated"
        return f"{action} {obj._meta.verbose_name}."

    def form_save(self, form):
        return form.save()

    def get_context_data(self, request, form):
        return {
            "model": self.get_queryset().model,
            "object": self.object,
            "form": form,
            "page_title": self.get_page_title(),
            "submit_label": self.get_submit_label(),
            "return_url": self.get_return_url(request, self.object),
            "is_editing": self.is_editing(),
            "show_add_another": self.get_show_add_another(),
            **self.get_extra_context(request, self.object),
        }

    def get(self, request, *args, **kwargs):
        form = self.get_form()
        return render(request, self.template_name, self.get_context_data(request, form))

    def post(self, request, *args, **kwargs):
        form = self.get_form(data=request.POST, files=request.FILES)
        if form.is_valid():
            addanother_url = self.get_addanother_url() if self.get_show_add_another() else None
            created = self.object.pk is None
            self.object = self.form_save(form)
            success_message = self.get_success_message(self.object, created)
            if success_message:
                messages.success(request, success_message)

            if "_addanother" in request.POST and addanother_url:
                return redirect(addanother_url)

            return redirect(self.get_return_url(request, self.object))

        return render(request, self.template_name, self.get_context_data(request, form))


class ObjectDeleteView(QuerysetBackedObjectView):
    template_name = "generic/object_delete.html"
    success_message = None

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object(**kwargs)
        return super().dispatch(request, *args, **kwargs)

    def get_cancel_url(self, request):
        return self.get_return_url(request, self.object)

    def get_success_message(self, obj):
        if self.success_message:
            return self.success_message
        return f"Deleted {obj._meta.verbose_name}."

    def get_delete_error_message(self, obj, error: ProtectedError):
        protected_counts = Counter()
        for protected_object in error.protected_objects:
            protected_counts[protected_object._meta] += 1

        if not protected_counts:
            return f"Cannot delete {obj._meta.verbose_name} because related records still exist."

        related_summaries = ", ".join(
            f"{count} {meta.verbose_name if count == 1 else meta.verbose_name_plural}"
            for meta, count in sorted(
                protected_counts.items(),
                key=lambda item: item[0].verbose_name,
            )
        )
        return (
            f"Cannot delete {obj._meta.verbose_name} because related records still exist: "
            f"{related_summaries}."
        )

    def get_context_data(self, request, *, delete_error=None):
        return {
            "object": self.object,
            "return_url": self.get_return_url(request, self.object),
            "cancel_url": self.get_cancel_url(request),
            "delete_error": delete_error,
            **self.get_extra_context(request, self.object),
        }

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self.get_context_data(request))

    def post(self, request, *args, **kwargs):
        success_message = self.get_success_message(self.object)
        try:
            self.object.delete()
        except ProtectedError as exc:
            delete_error = self.get_delete_error_message(self.object, exc)
            messages.error(request, delete_error)
            return render(
                request,
                self.template_name,
                self.get_context_data(request, delete_error=delete_error),
                status=409,
            )
        if success_message:
            messages.success(request, success_message)
        return redirect(self.get_return_url(request))


class ObjectListView(BaseMultiObjectView, TableMixin):
    template_name = "generic/object_list.html"
    filterset = None

    def get(self, request, *args, **kwargs):
        filterset = None
        queryset = self.queryset

        if self.filterset is not None:
            filterset = self.filterset(request.GET, queryset=queryset, request=request)
            queryset = filterset.qs
            apply_standard_widget_classes(filterset.form)

        table = self.get_table(queryset, request)

        context = {
            "model": queryset.model,
            "table": table,
            "filterset": filterset,
            "filter_form": filterset.form if filterset is not None else None,
            **self.get_extra_context(request),
        }

        return render(request, self.template_name, context)


class ObjectChangeLogView(QuerysetBackedObjectView):
    template_name = "generic/object_changelog.html"

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object(**kwargs)
        return super().dispatch(request, *args, **kwargs)

    def get_objectchanges(self):
        from django.contrib.contenttypes.models import ContentType
        from django.db.models import Q

        from core.models import ObjectChange

        content_type = ContentType.objects.get_for_model(
            self.object,
            for_concrete_model=False,
        )
        return ObjectChange.objects.select_related(
            "user",
            "changed_object_type",
            "related_object_type",
        ).filter(
            Q(changed_object_type=content_type, changed_object_id=self.object.pk)
            | Q(related_object_type=content_type, related_object_id=self.object.pk)
        )

    def get_context_data(self, request):
        object_context = self.build_object_context(self.object)
        object_context["active_tab"] = "changelog"
        object_context["changes"] = self.get_objectchanges()
        return {
            **object_context,
            **self.get_extra_context(request, self.object),
        }

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self.get_context_data(request))
