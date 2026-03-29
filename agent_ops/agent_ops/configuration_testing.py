ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

SECRET_KEY = "testing-secret-key-that-is-long-enough-for-agent-ops-auth-tests-12345"

DEBUG = True
LOGIN_REDIRECT_URL = "home"
TIME_ZONE = "UTC"
