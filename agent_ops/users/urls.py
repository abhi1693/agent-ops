from django.urls import path

from .views import (
    GroupCreateView,
    GroupDeleteView,
    GroupDetailView,
    GroupListView,
    GroupUpdateView,
    ObjectPermissionCreateView,
    ObjectPermissionDeleteView,
    ObjectPermissionDetailView,
    ObjectPermissionListView,
    ObjectPermissionUpdateView,
    UserCreateView,
    UserDeleteView,
    UserDetailView,
    UserListView,
    UserUpdateView,
)

urlpatterns = [
    path("users/", UserListView.as_view(), name="user_list"),
    path("users/add/", UserCreateView.as_view(), name="user_add"),
    path("users/<int:pk>/", UserDetailView.as_view(), name="user_detail"),
    path("users/<int:pk>/edit/", UserUpdateView.as_view(), name="user_edit"),
    path("users/<int:pk>/delete/", UserDeleteView.as_view(), name="user_delete"),
    path("groups/", GroupListView.as_view(), name="group_list"),
    path("groups/add/", GroupCreateView.as_view(), name="group_add"),
    path("groups/<int:pk>/", GroupDetailView.as_view(), name="group_detail"),
    path("groups/<int:pk>/edit/", GroupUpdateView.as_view(), name="group_edit"),
    path("groups/<int:pk>/delete/", GroupDeleteView.as_view(), name="group_delete"),
    path("permissions/", ObjectPermissionListView.as_view(), name="objectpermission_list"),
    path("permissions/add/", ObjectPermissionCreateView.as_view(), name="objectpermission_add"),
    path("permissions/<int:pk>/", ObjectPermissionDetailView.as_view(), name="objectpermission_detail"),
    path("permissions/<int:pk>/edit/", ObjectPermissionUpdateView.as_view(), name="objectpermission_edit"),
    path("permissions/<int:pk>/delete/", ObjectPermissionDeleteView.as_view(), name="objectpermission_delete"),
]
