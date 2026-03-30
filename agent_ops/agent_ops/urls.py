from django.urls import include, path

from account.views import AgentOpsLoginView, AgentOpsLogoutView
from core.views import HomeView, ObjectChangeListView

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("changelog/", ObjectChangeListView.as_view(), name="objectchange_list"),
    path("login/", AgentOpsLoginView.as_view(), name="login"),
    path("logout/", AgentOpsLogoutView.as_view(), name="logout"),
    path("api/", include(("agent_ops.api.urls", "api"), namespace="api")),
    path("automation/", include("automation.urls")),
    path("integrations/", include("integrations.urls")),
    path("tenancy/", include("tenancy.urls")),
    path("user/", include("account.urls")),
    path("users/", include("users.urls")),
]
