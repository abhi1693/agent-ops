from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from .views import APIRootView, StatusView


app_name = "api"

urlpatterns = [
    path("", APIRootView.as_view(), name="api-root"),
    path("users/", include(("users.api.urls", "users-api"), namespace="users-api")),
    path("status/", StatusView.as_view(), name="status"),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="api:schema"), name="swagger-ui"),
    path("schema/redoc/", SpectacularRedocView.as_view(url_name="api:schema"), name="redoc"),
]
