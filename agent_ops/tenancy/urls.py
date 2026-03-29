from django.urls import path

from .views import (
    EnvironmentCreateView,
    EnvironmentChangelogView,
    EnvironmentDeleteView,
    EnvironmentDetailView,
    EnvironmentListView,
    EnvironmentUpdateView,
    OrganizationCreateView,
    OrganizationChangelogView,
    OrganizationDeleteView,
    OrganizationDetailView,
    OrganizationListView,
    OrganizationUpdateView,
    WorkspaceCreateView,
    WorkspaceChangelogView,
    WorkspaceDeleteView,
    WorkspaceDetailView,
    WorkspaceListView,
    WorkspaceUpdateView,
)


urlpatterns = [
    path("organizations/", OrganizationListView.as_view(), name="organization_list"),
    path("organizations/add/", OrganizationCreateView.as_view(), name="organization_add"),
    path("organizations/<int:pk>/", OrganizationDetailView.as_view(), name="organization_detail"),
    path("organizations/<int:pk>/changelog/", OrganizationChangelogView.as_view(), name="organization_changelog"),
    path("organizations/<int:pk>/edit/", OrganizationUpdateView.as_view(), name="organization_edit"),
    path("organizations/<int:pk>/delete/", OrganizationDeleteView.as_view(), name="organization_delete"),
    path("workspaces/", WorkspaceListView.as_view(), name="workspace_list"),
    path("workspaces/add/", WorkspaceCreateView.as_view(), name="workspace_add"),
    path("workspaces/<int:pk>/", WorkspaceDetailView.as_view(), name="workspace_detail"),
    path("workspaces/<int:pk>/changelog/", WorkspaceChangelogView.as_view(), name="workspace_changelog"),
    path("workspaces/<int:pk>/edit/", WorkspaceUpdateView.as_view(), name="workspace_edit"),
    path("workspaces/<int:pk>/delete/", WorkspaceDeleteView.as_view(), name="workspace_delete"),
    path("environments/", EnvironmentListView.as_view(), name="environment_list"),
    path("environments/add/", EnvironmentCreateView.as_view(), name="environment_add"),
    path("environments/<int:pk>/", EnvironmentDetailView.as_view(), name="environment_detail"),
    path("environments/<int:pk>/changelog/", EnvironmentChangelogView.as_view(), name="environment_changelog"),
    path("environments/<int:pk>/edit/", EnvironmentUpdateView.as_view(), name="environment_edit"),
    path("environments/<int:pk>/delete/", EnvironmentDeleteView.as_view(), name="environment_delete"),
]
