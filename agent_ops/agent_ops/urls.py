from django.urls import include, path

from account.views import AgentOpsLoginView, AgentOpsLogoutView
from core.views import HomeView

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("login/", AgentOpsLoginView.as_view(), name="login"),
    path("logout/", AgentOpsLogoutView.as_view(), name="logout"),
    path("api/", include(("agent_ops.api.urls", "api"), namespace="api")),
    path("user/", include("account.urls")),
    path("users/", include("users.urls")),
]
