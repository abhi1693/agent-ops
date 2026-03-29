from core.navigation import Menu, MenuGroup, MenuItem


TENANCY_MENU = Menu(
    label="Tenancy",
    icon_class="mdi mdi-domain",
    staff_only=True,
    groups=(
        MenuGroup(
            label="Tenant Scope",
            items=(
                MenuItem(
                    link="organization_list",
                    link_text="Organizations",
                    icon_class="mdi mdi-office-building-outline",
                    add_link="organization_add",
                    add_button_label="Add organization",
                    active_links=(
                        "organization_list",
                        "organization_add",
                        "organization_detail",
                        "organization_edit",
                    ),
                    staff_only=True,
                ),
                MenuItem(
                    link="workspace_list",
                    link_text="Workspaces",
                    icon_class="mdi mdi-briefcase-outline",
                    add_link="workspace_add",
                    add_button_label="Add workspace",
                    active_links=(
                        "workspace_list",
                        "workspace_add",
                        "workspace_detail",
                        "workspace_edit",
                    ),
                    staff_only=True,
                ),
                MenuItem(
                    link="environment_list",
                    link_text="Environments",
                    icon_class="mdi mdi-cloud-outline",
                    add_link="environment_add",
                    add_button_label="Add environment",
                    active_links=(
                        "environment_list",
                        "environment_add",
                        "environment_detail",
                        "environment_edit",
                    ),
                    staff_only=True,
                ),
            ),
        ),
    ),
)


def get_navigation_menus(_request):
    return (TENANCY_MENU,)
