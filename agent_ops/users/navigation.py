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
                    add_link="user_add",
                    add_button_label="Add user",
                    active_links=("user_list", "user_add", "user_detail", "user_edit"),
                    staff_only=True,
                ),
                MenuItem(
                    link="group_list",
                    link_text="Groups",
                    icon_class="mdi mdi-account-group-outline",
                    add_link="group_add",
                    add_button_label="Add group",
                    active_links=("group_list", "group_add", "group_detail", "group_edit"),
                    staff_only=True,
                ),
                MenuItem(
                    link="membership_list",
                    link_text="Memberships",
                    icon_class="mdi mdi-account-key-outline",
                    add_link="membership_add",
                    add_button_label="Add membership",
                    active_links=(
                        "membership_list",
                        "membership_add",
                        "membership_detail",
                        "membership_edit",
                    ),
                    staff_only=True,
                ),
                MenuItem(
                    link="objectpermission_list",
                    link_text="Object Permissions",
                    icon_class="mdi mdi-shield-key-outline",
                    add_link="objectpermission_add",
                    add_button_label="Add object permission",
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
