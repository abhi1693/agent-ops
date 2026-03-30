from core.navigation import Menu, MenuGroup, MenuItem
from integrations.models import Secret, SecretGroup, SecretGroupAssignment
from users.restrictions import has_model_action_permission


def get_navigation_menus(request):
    secret_allowed = has_model_action_permission(Secret, request=request, action="view")
    secret_group_allowed = has_model_action_permission(SecretGroup, request=request, action="view")
    secret_group_assignment_allowed = has_model_action_permission(
        SecretGroupAssignment,
        request=request,
        action="view",
    )
    if not secret_allowed and not secret_group_allowed and not secret_group_assignment_allowed:
        return ()

    items = []
    if secret_allowed:
        items.append(
            MenuItem(
                link="secret_list",
                link_text="Secrets",
                icon_class="mdi mdi-key-chain-variant",
                add_link="secret_add" if has_model_action_permission(Secret, request=request, action="add") else None,
                add_button_label="Add secret",
                active_links=("secret_list", "secret_add", "secret_detail", "secret_edit"),
                auth_required=True,
            )
        )
    if secret_group_allowed:
        items.append(
            MenuItem(
                link="secretgroup_list",
                link_text="Secret Groups",
                icon_class="mdi mdi-folder-key-network",
                add_link="secretgroup_add" if has_model_action_permission(SecretGroup, request=request, action="add") else None,
                add_button_label="Add secret group",
                active_links=("secretgroup_list", "secretgroup_add", "secretgroup_detail", "secretgroup_edit"),
                auth_required=True,
            )
        )
    if secret_group_assignment_allowed:
        items.append(
            MenuItem(
                link="secretgroupassignment_list",
                link_text="Assignments",
                icon_class="mdi mdi-key-link",
                add_link=(
                    "secretgroupassignment_add"
                    if has_model_action_permission(SecretGroupAssignment, request=request, action="add")
                    else None
                ),
                add_button_label="Add assignment",
                active_links=(
                    "secretgroupassignment_list",
                    "secretgroupassignment_add",
                    "secretgroupassignment_detail",
                    "secretgroupassignment_edit",
                ),
                auth_required=True,
            )
        )

    return (
        Menu(
            label="Integrations",
            icon_class="mdi mdi-connection",
            auth_required=True,
            groups=(
                MenuGroup(
                    label="Secrets",
                    items=tuple(items),
                ),
            ),
        ),
    )
