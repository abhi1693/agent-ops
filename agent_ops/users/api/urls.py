from django.urls import path
from rest_framework.routers import DefaultRouter

from .viewsets import (
    GroupViewSet,
    MembershipViewSet,
    ObjectPermissionViewSet,
    TokenViewSet,
    UserConfigView,
    UserViewSet,
    UsersRootView,
)


app_name = "users-api"

router = DefaultRouter()
router.APIRootView = UsersRootView
router.register("groups", GroupViewSet, basename="group")
router.register("memberships", MembershipViewSet, basename="membership")
router.register("permissions", ObjectPermissionViewSet, basename="objectpermission")
router.register("tokens", TokenViewSet, basename="token")
router.register("users", UserViewSet, basename="user")

urlpatterns = [
    path("config/", UserConfigView.as_view(), name="config"),
]
urlpatterns += router.urls
