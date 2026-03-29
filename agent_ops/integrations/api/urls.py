from rest_framework.routers import DefaultRouter

from .viewsets import IntegrationsRootView, SecretViewSet


router = DefaultRouter()
router.APIRootView = IntegrationsRootView
router.register("secrets", SecretViewSet, basename="secret")

urlpatterns = router.urls
