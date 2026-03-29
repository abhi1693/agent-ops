from django.contrib.auth.views import LogoutView
from django.urls import path, reverse_lazy

from .views import AgentOpsLoginView, HomeView

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("login/", AgentOpsLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(next_page=reverse_lazy("login")), name="logout"),
]
