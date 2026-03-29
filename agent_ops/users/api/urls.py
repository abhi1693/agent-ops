from rest_framework.routers import DefaultRouter

from .viewsets import GroupViewSet, UserViewSet


app_name = "users-api"

router = DefaultRouter()
router.register("groups", GroupViewSet, basename="group")
router.register("users", UserViewSet, basename="user")

urlpatterns = router.urls
