from rest_framework.routers import DefaultRouter

from .viewsets import EnvironmentViewSet, OrganizationViewSet, TenancyRootView, WorkspaceViewSet


app_name = "tenancy-api"

router = DefaultRouter()
router.APIRootView = TenancyRootView
router.register("organizations", OrganizationViewSet, basename="organization")
router.register("workspaces", WorkspaceViewSet, basename="workspace")
router.register("environments", EnvironmentViewSet, basename="environment")

urlpatterns = router.urls
