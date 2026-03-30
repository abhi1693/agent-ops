from django.urls import path

from .views import (
    WorkflowChangelogView,
    WorkflowCreateView,
    WorkflowDeleteView,
    WorkflowDesignerView,
    WorkflowDetailView,
    WorkflowListView,
    WorkflowUpdateView,
    WorkflowWebhookTriggerView,
)


urlpatterns = [
    path("workflows/", WorkflowListView.as_view(), name="workflow_list"),
    path("workflows/add/", WorkflowCreateView.as_view(), name="workflow_add"),
    path("workflows/<int:pk>/", WorkflowDetailView.as_view(), name="workflow_detail"),
    path("workflows/<int:pk>/designer/", WorkflowDesignerView.as_view(), name="workflow_designer"),
    path("workflows/<int:pk>/trigger/webhook/", WorkflowWebhookTriggerView.as_view(), name="workflow_webhook_trigger"),
    path("workflows/<int:pk>/changelog/", WorkflowChangelogView.as_view(), name="workflow_changelog"),
    path("workflows/<int:pk>/edit/", WorkflowUpdateView.as_view(), name="workflow_edit"),
    path("workflows/<int:pk>/delete/", WorkflowDeleteView.as_view(), name="workflow_delete"),
]
