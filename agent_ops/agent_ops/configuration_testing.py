ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

SECRET_KEY = "testing-secret-key-that-is-long-enough-for-agent-ops-auth-tests-12345"

DEBUG = True
HOSTNAME = "testserver"
LOGIN_REDIRECT_URL = "home"
REDIS = {
    "tasks": {
        "HOST": "localhost",
        "PORT": 6379,
        "DB": 15,
    },
    "caching": {
        "HOST": "localhost",
        "PORT": 6379,
        "DB": 14,
    },
}
TIME_ZONE = "UTC"
