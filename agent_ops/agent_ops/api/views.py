import platform

from django import __version__ as DJANGO_VERSION
from django.apps import apps
from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.views import APIView

from .permissions import TokenPermissions


class APIRootView(APIView):
    permission_classes = [TokenPermissions]

    def get_view_name(self):
        return "API Root"

    @extend_schema(exclude=True)
    def get(self, request, format=None):
        return Response(
            {
                "changelog": reverse("api:changelog-list", request=request, format=format),
                "integrations": reverse("api:integrations-api:api-root", request=request, format=format),
                "tenancy": reverse("api:tenancy-api:api-root", request=request, format=format),
                "users": reverse("api:users-api:api-root", request=request, format=format),
                "status": reverse("api:status", request=request, format=format),
            }
        )


class StatusView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        return Response(
            {
                "django-version": DJANGO_VERSION,
                "hostname": settings.HOSTNAME,
                "installed_apps": [app.label for app in apps.get_app_configs()],
                "python-version": platform.python_version(),
            }
        )
