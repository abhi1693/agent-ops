from django.urls import path

from .views import (
    PreferenceUpdateView,
    ProfileScopeUpdateView,
    ProfileUpdateView,
    ProfileView,
    TokenCreateView,
    TokenDeleteView,
    TokenListView,
)

urlpatterns = [
    path("profile/", ProfileView.as_view(), name="profile"),
    path("profile/edit/", ProfileUpdateView.as_view(), name="profile_edit"),
    path("profile/scope/", ProfileScopeUpdateView.as_view(), name="profile_scope"),
    path("preferences/", PreferenceUpdateView.as_view(), name="preferences"),
    path("api-tokens/", TokenListView.as_view(), name="token_list"),
    path("api-tokens/add/", TokenCreateView.as_view(), name="token_add"),
    path("api-tokens/<int:pk>/delete/", TokenDeleteView.as_view(), name="token_delete"),
]
