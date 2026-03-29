from django import forms

from core.form_widgets import apply_standard_widget_classes
from tenancy.models import Environment, Organization, Workspace
from users.restrictions import restrict_queryset


class OrganizationForm(forms.ModelForm):
    fieldsets = (
        {
            "title": "Organization",
            "fields": ("name", "description"),
        },
    )

    class Meta:
        model = Organization
        fields = ("name", "description")

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        apply_standard_widget_classes(self)


class WorkspaceForm(forms.ModelForm):
    fieldsets = (
        {
            "title": "Workspace",
            "fields": ("organization", "name", "description"),
        },
    )
    organization = forms.ModelChoiceField(
        queryset=Organization.objects.none(),
    )

    class Meta:
        model = Workspace
        fields = ("organization", "name", "description")

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = Organization.objects.order_by("name")
        if request is not None:
            queryset = restrict_queryset(queryset, request=request, action="view")
        self.fields["organization"].queryset = queryset
        apply_standard_widget_classes(self)


class EnvironmentForm(forms.ModelForm):
    fieldsets = (
        {
            "title": "Environment",
            "fields": ("workspace", "name", "description"),
        },
    )
    workspace = forms.ModelChoiceField(
        queryset=Workspace.objects.none(),
    )

    class Meta:
        model = Environment
        fields = ("workspace", "name", "description")

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = Workspace.objects.select_related("organization").order_by(
            "organization__name", "name"
        )
        if request is not None:
            queryset = restrict_queryset(queryset, request=request, action="view")
        self.fields["workspace"].queryset = queryset
        apply_standard_widget_classes(self)
