from rest_framework.routers import DefaultRouter

from .viewsets import AutomationRootView, WorkflowViewSet


router = DefaultRouter()
router.APIRootView = AutomationRootView
router.register("workflows", WorkflowViewSet, basename="workflow")

urlpatterns = router.urls

