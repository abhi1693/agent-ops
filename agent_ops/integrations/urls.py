from django.urls import path

from .views import (
    SecretChangelogView,
    SecretCreateView,
    SecretDeleteView,
    SecretDetailView,
    SecretListView,
    SecretUpdateView,
    SecretGroupChangelogView,
    SecretGroupCreateView,
    SecretGroupDeleteView,
    SecretGroupDetailView,
    SecretGroupListView,
    SecretGroupUpdateView,
    SecretGroupAssignmentChangelogView,
    SecretGroupAssignmentCreateView,
    SecretGroupAssignmentDeleteView,
    SecretGroupAssignmentDetailView,
    SecretGroupAssignmentListView,
    SecretGroupAssignmentUpdateView,
)


urlpatterns = [
    path("secrets/", SecretListView.as_view(), name="secret_list"),
    path("secrets/add/", SecretCreateView.as_view(), name="secret_add"),
    path("secrets/<int:pk>/", SecretDetailView.as_view(), name="secret_detail"),
    path("secrets/<int:pk>/changelog/", SecretChangelogView.as_view(), name="secret_changelog"),
    path("secrets/<int:pk>/edit/", SecretUpdateView.as_view(), name="secret_edit"),
    path("secrets/<int:pk>/delete/", SecretDeleteView.as_view(), name="secret_delete"),
    path("secret-groups/", SecretGroupListView.as_view(), name="secretgroup_list"),
    path("secret-groups/add/", SecretGroupCreateView.as_view(), name="secretgroup_add"),
    path("secret-groups/<int:pk>/", SecretGroupDetailView.as_view(), name="secretgroup_detail"),
    path("secret-groups/<int:pk>/changelog/", SecretGroupChangelogView.as_view(), name="secretgroup_changelog"),
    path("secret-groups/<int:pk>/edit/", SecretGroupUpdateView.as_view(), name="secretgroup_edit"),
    path("secret-groups/<int:pk>/delete/", SecretGroupDeleteView.as_view(), name="secretgroup_delete"),
    path("secret-group-assignments/", SecretGroupAssignmentListView.as_view(), name="secretgroupassignment_list"),
    path("secret-group-assignments/add/", SecretGroupAssignmentCreateView.as_view(), name="secretgroupassignment_add"),
    path("secret-group-assignments/<int:pk>/", SecretGroupAssignmentDetailView.as_view(), name="secretgroupassignment_detail"),
    path(
        "secret-group-assignments/<int:pk>/changelog/",
        SecretGroupAssignmentChangelogView.as_view(),
        name="secretgroupassignment_changelog",
    ),
    path("secret-group-assignments/<int:pk>/edit/", SecretGroupAssignmentUpdateView.as_view(), name="secretgroupassignment_edit"),
    path("secret-group-assignments/<int:pk>/delete/", SecretGroupAssignmentDeleteView.as_view(), name="secretgroupassignment_delete"),
]
