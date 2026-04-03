from rest_framework.routers import DefaultRouter

from .viewsets import (
    AutomationRootView,
    SecretGroupViewSet,
    SecretViewSet,
    WorkflowRunViewSet,
    WorkflowViewSet,
)


router = DefaultRouter()
router.APIRootView = AutomationRootView
router.register("secrets", SecretViewSet, basename="secret")
router.register("secret-groups", SecretGroupViewSet, basename="secretgroup")
router.register("workflows", WorkflowViewSet, basename="workflow")
router.register("workflow-runs", WorkflowRunViewSet, basename="workflowrun")

urlpatterns = router.urls
