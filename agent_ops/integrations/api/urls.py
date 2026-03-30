from rest_framework.routers import DefaultRouter

from .viewsets import (
    IntegrationsRootView,
    SecretGroupAssignmentViewSet,
    SecretGroupViewSet,
    SecretViewSet,
)


router = DefaultRouter()
router.APIRootView = IntegrationsRootView
router.register("secrets", SecretViewSet, basename="secret")
router.register("secret-groups", SecretGroupViewSet, basename="secretgroup")
router.register("secret-group-assignments", SecretGroupAssignmentViewSet, basename="secretgroupassignment")

urlpatterns = router.urls
