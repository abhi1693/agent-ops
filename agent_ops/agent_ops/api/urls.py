from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from core.api.viewsets import ObjectChangeViewSet

from .views import APIRootView, StatusView


app_name = "api"

urlpatterns = [
    path("", APIRootView.as_view(), name="api-root"),
    path("changelog/", ObjectChangeViewSet.as_view({"get": "list"}), name="changelog-list"),
    path("changelog/<int:pk>/", ObjectChangeViewSet.as_view({"get": "retrieve"}), name="changelog-detail"),
    path("automation/", include(("automation.api.urls", "automation-api"), namespace="automation-api")),
    path("integrations/", include(("integrations.api.urls", "integrations-api"), namespace="integrations-api")),
    path("tenancy/", include(("tenancy.api.urls", "tenancy-api"), namespace="tenancy-api")),
    path("users/", include(("users.api.urls", "users-api"), namespace="users-api")),
    path("status/", StatusView.as_view(), name="status"),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="api:schema"), name="swagger-ui"),
    path("schema/redoc/", SpectacularRedocView.as_view(url_name="api:schema"), name="redoc"),
]
