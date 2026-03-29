import socket

from users.preferences import DEFAULT_USER_PREFERENCES


def agent_ops_ui(request):
    theme = DEFAULT_USER_PREFERENCES["ui"]["theme"]
    if getattr(request, "user", None) and request.user.is_authenticated:
        theme = request.user.get_config().get("ui.theme")

    return {
        "agent_ops_ui": {
            "app_name": "Agent Ops",
            "app_edition": "Users Module",
            "release_name": "First-Party Identity",
            "hostname": socket.gethostname(),
            "theme": theme,
        }
    }
