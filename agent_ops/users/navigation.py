from core.navigation import Menu, MenuGroup, MenuItem


ADMINISTRATION_MENU = Menu(
    label="Administration",
    icon_class="mdi mdi-account-multiple",
    staff_only=True,
    groups=(
        MenuGroup(
            label="Authentication",
            items=(
                MenuItem(
                    link="user_list",
                    link_text="Users",
                    icon_class="mdi mdi-account-outline",
                    active_links=("user_list", "user_add", "user_detail", "user_edit"),
                    staff_only=True,
                ),
                MenuItem(
                    link="group_list",
                    link_text="Groups",
                    icon_class="mdi mdi-account-group-outline",
                    active_links=("group_list", "group_add", "group_detail", "group_edit"),
                    staff_only=True,
                ),
                MenuItem(
                    link="objectpermission_list",
                    link_text="Object Permissions",
                    icon_class="mdi mdi-shield-key-outline",
                    active_links=(
                        "objectpermission_list",
                        "objectpermission_add",
                        "objectpermission_detail",
                        "objectpermission_edit",
                    ),
                    staff_only=True,
                ),
            ),
        ),
    ),
)


def get_navigation_menus(_request):
    return (ADMINISTRATION_MENU,)
