import json

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from automation.auth import list_workflow_secret_group_options
from automation import filtersets, tables
from automation.forms import WorkflowDesignerForm, WorkflowForm, WorkflowRunForm
from automation.models import Workflow, WorkflowRun
from automation.primitives import WORKFLOW_NODE_TEMPLATES, normalize_workflow_definition_nodes
from automation.runtime import execute_workflow
from automation.triggers import prepare_webhook_trigger_request
from core.generic_views import (
    ObjectChangeLogView,
    ObjectDeleteView,
    ObjectEditView,
    ObjectListView,
    ObjectView,
)
from tenancy.mixins import (
    RestrictedObjectChangeLogMixin,
    RestrictedObjectDeleteMixin,
    RestrictedObjectEditMixin,
    RestrictedObjectListMixin,
    RestrictedObjectViewMixin,
)
from users.restrictions import assert_object_action_allowed


def _pretty_json(value):
    if value in (None, "", {}, []):
        return None
    return json.dumps(value, indent=2, sort_keys=True)


def _build_run_display(run: WorkflowRun):
    return {
        "object": run,
        "input_json": _pretty_json(run.input_data),
        "output_json": _pretty_json(run.output_data),
        "context_json": _pretty_json(run.context_data),
        "steps_json": _pretty_json(run.step_results),
    }


def _hydrate_workflow_node_templates(*, secret_group_options):
    hydrated_templates = []
    for template in WORKFLOW_NODE_TEMPLATES:
        hydrated_template = dict(template)
        hydrated_fields = []
        for field in template.get("fields", ()):
            hydrated_field = dict(field)
            if hydrated_field.get("key") == "auth_secret_group_id":
                hydrated_field["options"] = list(secret_group_options)
            hydrated_fields.append(hydrated_field)
        hydrated_template["fields"] = hydrated_fields
        hydrated_templates.append(hydrated_template)
    return hydrated_templates


def _group_workflow_node_templates_by_app(*, node_templates):
    grouped_templates = []
    app_index = {}

    for template in node_templates:
        app_id = template.get("app_id") or "builtins"
        app_group = app_index.get(app_id)
        if app_group is None:
            app_group = {
                "id": app_id,
                "label": template.get("app_label") or "Built-ins",
                "description": template.get("app_description") or "",
                "icon": template.get("app_icon") or "mdi-vector-square",
                "templates": [],
            }
            app_index[app_id] = app_group
            grouped_templates.append(app_group)
        app_group["templates"].append(template)

    return grouped_templates


class WorkflowListView(RestrictedObjectListMixin, ObjectListView):
    queryset = Workflow.objects.select_related("organization", "workspace", "environment")
    table = tables.WorkflowTable
    filterset = filtersets.WorkflowFilterSet
    template_name = "automation/workflow_list.html"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("organization", "workspace", "environment")
            .order_by("organization__name", "workspace__name", "environment__name", "name")
        )


class WorkflowDetailView(RestrictedObjectViewMixin, ObjectView):
    model = Workflow
    template_name = "automation/workflow_detail.html"

    def get_queryset(self):
        return super().get_queryset().select_related("organization", "workspace", "environment")

    def get_context_data(self, **kwargs):
        run_form = kwargs.pop("run_form", None) or WorkflowRunForm(initial={"input_data": {}})
        context = super().get_context_data(**kwargs)
        normalized_definition = normalize_workflow_definition_nodes(self.object.definition)
        recent_runs = list(self.object.runs.order_by("-created")[:5])
        context["show_side_panel"] = True
        context["can_design"] = context["can_edit"]
        context["can_execute"] = context["can_edit"]
        context["workflow_nodes"] = normalized_definition.get("nodes", [])
        context["workflow_edges"] = normalized_definition.get("edges", [])
        context["workflow_designer_url"] = reverse("workflow_designer", args=[self.object.pk])
        context["run_form"] = run_form
        context["latest_run"] = _build_run_display(recent_runs[0]) if recent_runs else None
        context["recent_runs"] = [_build_run_display(run) for run in recent_runs]
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        assert_object_action_allowed(
            self.object,
            request=request,
            action="change",
        )
        run_form = WorkflowRunForm(request.POST)
        if not run_form.is_valid():
            context = self.get_context_data(object=self.object, run_form=run_form)
            return self.render_to_response(context)

        run = execute_workflow(
            self.object,
            input_data=run_form.cleaned_data.get("input_data") or {},
            actor=request.user,
        )
        if run.status == WorkflowRun.StatusChoices.SUCCEEDED:
            messages.success(request, "Workflow executed.")
        else:
            messages.error(request, f"Workflow execution failed. {run.error}".strip())
        return redirect(self.object.get_absolute_url())


class WorkflowChangelogView(RestrictedObjectChangeLogMixin, ObjectChangeLogView):
    model = Workflow
    queryset = Workflow.objects.select_related("organization", "workspace", "environment").order_by(
        "organization__name",
        "workspace__name",
        "environment__name",
        "name",
    )


class WorkflowCreateView(RestrictedObjectEditMixin, ObjectEditView):
    model = Workflow
    form_class = WorkflowForm
    success_message = "Workflow created."


class WorkflowUpdateView(RestrictedObjectEditMixin, ObjectEditView):
    model = Workflow
    form_class = WorkflowForm
    success_message = "Workflow updated."


class WorkflowDesignerView(RestrictedObjectEditMixin, ObjectEditView):
    model = Workflow
    form_class = WorkflowDesignerForm
    template_name = "automation/workflow_designer.html"
    success_message = "Workflow designer updated."
    submit_label = "Save workflow"
    show_add_another = False

    def get_page_title(self):
        return f"Designer: {self.object}"

    def get_return_url(self, request, obj=None):
        workflow = obj or self.object
        return reverse("workflow_designer", args=[workflow.pk])

    def get_context_data(self, request, form):
        context = super().get_context_data(request, form)
        normalized_definition = normalize_workflow_definition_nodes(self.object.definition)
        secret_group_options = list_workflow_secret_group_options(self.object)
        hydrated_templates = _hydrate_workflow_node_templates(
            secret_group_options=secret_group_options,
        )
        context.update(
            {
                "workflow_definition": normalized_definition,
                "workflow_nodes": normalized_definition.get("nodes", []),
                "workflow_node_templates": hydrated_templates,
                "workflow_node_template_groups": _group_workflow_node_templates_by_app(
                    node_templates=hydrated_templates,
                ),
                "workflow_list_url": reverse("workflow_list"),
                "workflow_detail_url": self.object.get_absolute_url(),
                "workflow_edit_url": reverse("workflow_edit", args=[self.object.pk]),
                "workflow_changelog_url": reverse("workflow_changelog", args=[self.object.pk]),
            }
        )
        return context


class WorkflowDeleteView(RestrictedObjectDeleteMixin, ObjectDeleteView):
    model = Workflow
    success_message = "Workflow deleted."


@method_decorator(csrf_exempt, name="dispatch")
class WorkflowWebhookTriggerView(View):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        workflow = (
            Workflow.objects.select_related("organization", "workspace", "environment")
            .filter(pk=kwargs["pk"], enabled=True)
            .first()
        )
        if workflow is None:
            return JsonResponse({"detail": "Workflow not found."}, status=404)

        nodes = normalize_workflow_definition_nodes(workflow.definition or {}).get("nodes", [])
        trigger_node = next((node for node in nodes if node.get("kind") == "trigger"), None)
        if trigger_node is None:
            return JsonResponse({"detail": "Workflow has no trigger node."}, status=400)

        try:
            trigger_mode, input_data, trigger_metadata = prepare_webhook_trigger_request(
                workflow=workflow,
                node=trigger_node,
                request=request,
            )
        except ValidationError as exc:
            message = " ".join(exc.messages)
            return JsonResponse({"detail": message}, status=400)

        run = execute_workflow(
            workflow,
            input_data=input_data,
            trigger_mode=trigger_mode,
            trigger_metadata=trigger_metadata,
            actor=None,
        )
        status_code = 200 if run.status == WorkflowRun.StatusChoices.SUCCEEDED else 400
        return JsonResponse(
            {
                "run_id": run.pk,
                "status": run.status,
                "error": run.error,
                "output_data": run.output_data,
            },
            status=status_code,
        )
