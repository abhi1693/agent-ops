from django.urls import path

from .views import (
    SecretChangelogView,
    SecretCreateView,
    SecretDeleteView,
    SecretDetailView,
    SecretListView,
    SecretUpdateView,
)


urlpatterns = [
    path("secrets/", SecretListView.as_view(), name="secret_list"),
    path("secrets/add/", SecretCreateView.as_view(), name="secret_add"),
    path("secrets/<int:pk>/", SecretDetailView.as_view(), name="secret_detail"),
    path("secrets/<int:pk>/changelog/", SecretChangelogView.as_view(), name="secret_changelog"),
    path("secrets/<int:pk>/edit/", SecretUpdateView.as_view(), name="secret_edit"),
    path("secrets/<int:pk>/delete/", SecretDeleteView.as_view(), name="secret_delete"),
]
