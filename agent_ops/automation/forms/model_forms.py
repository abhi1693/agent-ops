from django import forms

from automation.models import Workflow
from automation.primitives import normalize_workflow_definition_nodes
from core.form_widgets import apply_standard_widget_classes
from tenancy.models import Environment, Organization, Workspace
from users.restrictions import restrict_queryset


def _configure_scope_fields(form, request):
    organization_qs = Organization.objects.order_by("name")
    workspace_qs = Workspace.objects.select_related("organization").order_by("organization__name", "name")
    environment_qs = Environment.objects.select_related("organization", "workspace").order_by(
        "organization__name",
        "workspace__name",
        "name",
    )

    if request is not None:
        organization_qs = restrict_queryset(organization_qs, request=request, action="view")
        workspace_qs = restrict_queryset(workspace_qs, request=request, action="view")
        environment_qs = restrict_queryset(environment_qs, request=request, action="view")

    form.fields["organization"].queryset = organization_qs
    form.fields["workspace"].queryset = workspace_qs
    form.fields["environment"].queryset = environment_qs


class WorkflowForm(forms.ModelForm):
    fieldsets = (
        {
            "title": "Workflow",
            "fields": (
                "organization",
                "workspace",
                "environment",
                "name",
                "description",
                "enabled",
            ),
        },
        {
            "title": "Metadata",
            "description": "Store designer-level metadata here. The graph itself is edited in the workflow designer.",
            "fields": ("metadata",),
        },
    )
    organization = forms.ModelChoiceField(queryset=Organization.objects.none(), required=False)
    workspace = forms.ModelChoiceField(queryset=Workspace.objects.none(), required=False)
    environment = forms.ModelChoiceField(queryset=Environment.objects.none(), required=False)

    class Meta:
        model = Workflow
        fields = (
            "organization",
            "workspace",
            "environment",
            "name",
            "description",
            "enabled",
            "metadata",
        )

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        _configure_scope_fields(self, request)
        self.fields["metadata"].widget.attrs["rows"] = 6
        apply_standard_widget_classes(self)


class WorkflowDesignerForm(forms.ModelForm):
    definition = forms.JSONField(widget=forms.HiddenInput())

    class Meta:
        model = Workflow
        fields = ("definition",)

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and getattr(self.instance, "pk", None):
            self.initial["definition"] = normalize_workflow_definition_nodes(self.instance.definition)
        apply_standard_widget_classes(self)

    def clean_definition(self):
        definition = self.cleaned_data["definition"]
        return normalize_workflow_definition_nodes(definition)


class WorkflowRunForm(forms.Form):
    input_data = forms.JSONField(
        required=False,
        initial=dict,
        widget=forms.Textarea,
        help_text="Manual trigger payload. Available during execution as trigger.payload.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["input_data"].widget.attrs["rows"] = 8
        apply_standard_widget_classes(self)
