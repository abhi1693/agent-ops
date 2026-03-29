import importlib
import os
import platform
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

if sys.version_info < (3, 12):  # noqa: UP036
    raise RuntimeError(
        f"Agent Ops requires Python 3.12 or later. (Currently installed: Python {platform.python_version()})"
    )


config_path = os.getenv("AGENT_OPS_CONFIGURATION", "agent_ops.configuration")
try:
    configuration = importlib.import_module(config_path)
except ModuleNotFoundError as exc:
    if getattr(exc, "name") == config_path:
        raise ImproperlyConfigured(
            f"Specified configuration module ({config_path}) not found. "
            "Define agent_ops/configuration.py or set AGENT_OPS_CONFIGURATION to an importable module."
        ) from exc
    raise

for parameter in ("ALLOWED_HOSTS", "SECRET_KEY"):
    if not hasattr(configuration, parameter):
        raise ImproperlyConfigured(f"Required parameter {parameter} is missing from configuration.")

if not hasattr(configuration, "DATABASES"):
    raise ImproperlyConfigured("The database configuration must be defined using DATABASES.")


ALLOWED_HOSTS = getattr(configuration, "ALLOWED_HOSTS")
DATABASES = getattr(configuration, "DATABASES")
DEBUG = getattr(configuration, "DEBUG", False)
HOSTNAME = getattr(configuration, "HOSTNAME", platform.node())
LANGUAGE_CODE = getattr(configuration, "LANGUAGE_CODE", "en-us")
LOGIN_REDIRECT_URL = getattr(configuration, "LOGIN_REDIRECT_URL", "home")
SECRET_KEY = getattr(configuration, "SECRET_KEY")
TIME_ZONE = getattr(configuration, "TIME_ZONE", "UTC")

if not isinstance(SECRET_KEY, str):
    raise ImproperlyConfigured(f"SECRET_KEY must be a string (found {type(SECRET_KEY).__name__})")
if len(SECRET_KEY) < 50:
    raise ImproperlyConfigured("SECRET_KEY must be at least 50 characters in length.")

if "default" not in DATABASES:
    raise ImproperlyConfigured("No default database has been configured.")

if "ENGINE" not in DATABASES["default"]:
    DATABASES["default"]["ENGINE"] = "django.db.backends.postgresql"

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "drf_spectacular",
    "django_filters",
    "django_tables2",
    "rest_framework",
    "core.apps.CoreConfig",
    "account.apps.AccountConfig",
    "users.apps.UsersConfig",
]

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.security.SecurityMiddleware",
]

ROOT_URLCONF = "agent_ops.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.agent_ops_ui",
            ],
        },
    }
]

WSGI_APPLICATION = "agent_ops.wsgi.application"
ASGI_APPLICATION = "agent_ops.asgi.application"

USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "project-static"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "users.User"
AUTHENTICATION_BACKENDS = getattr(
    configuration,
    "AUTHENTICATION_BACKENDS",
    ["users.auth_backends.UsernameOrEmailBackend"],
)
LOGIN_URL = "login"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.SessionAuthentication",
        "agent_ops.api.authentication.TokenAuthentication",
    ),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "DEFAULT_PARSER_CLASSES": (
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "agent_ops.api.permissions.TokenPermissions",
    ),
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "PAGE_SIZE": getattr(configuration, "API_DEFAULT_PAGE_SIZE", 50),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Agent Ops API",
    "DESCRIPTION": "REST API for Agent Ops.",
    "VERSION": "1.0",
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAuthenticated"],
}
