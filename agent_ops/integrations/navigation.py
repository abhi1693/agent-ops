from core.navigation import Menu, MenuGroup, MenuItem
from integrations.models import Secret
from users.restrictions import has_model_action_permission


def get_navigation_menus(request):
    if not has_model_action_permission(Secret, request=request, action="view"):
        return ()

    return (
        Menu(
            label="Integrations",
            icon_class="mdi mdi-connection",
            auth_required=True,
            groups=(
                MenuGroup(
                    label="Secrets",
                    items=(
                        MenuItem(
                            link="secret_list",
                            link_text="Secrets",
                            icon_class="mdi mdi-key-chain-variant",
                            add_link="secret_add" if has_model_action_permission(Secret, request=request, action="add") else None,
                            add_button_label="Add secret",
                            active_links=("secret_list", "secret_add", "secret_detail", "secret_edit"),
                            auth_required=True,
                        ),
                    ),
                ),
            ),
        ),
    )
