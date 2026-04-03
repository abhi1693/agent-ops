from automation.models import Secret, SecretGroup, Workflow, WorkflowConnection
from core.navigation import Menu, MenuGroup, MenuItem
from users.restrictions import has_model_action_permission


def get_navigation_menus(request):
    workflow_allowed = has_model_action_permission(Workflow, request=request, action="view")
    workflow_connection_allowed = has_model_action_permission(WorkflowConnection, request=request, action="view")
    secret_allowed = has_model_action_permission(Secret, request=request, action="view")
    secret_group_allowed = has_model_action_permission(SecretGroup, request=request, action="view")
    if not workflow_allowed and not workflow_connection_allowed and not secret_allowed and not secret_group_allowed:
        return ()

    workflow_items = []
    if workflow_allowed:
        workflow_items.append(
            MenuItem(
                link="workflow_list",
                link_text="Workflows",
                icon_class="mdi mdi-graph-outline",
                add_link="workflow_add" if has_model_action_permission(Workflow, request=request, action="add") else None,
                add_button_label="Add workflow",
                active_links=(
                    "workflow_list",
                    "workflow_add",
                    "workflow_detail",
                    "workflow_edit",
                    "workflow_designer",
                ),
                auth_required=True,
            )
        )
    if workflow_connection_allowed:
        workflow_items.append(
            MenuItem(
                link="workflowconnection_list",
                link_text="Connections",
                icon_class="mdi mdi-connection",
                add_link=(
                    "workflowconnection_add"
                    if has_model_action_permission(WorkflowConnection, request=request, action="add")
                    else None
                ),
                add_button_label="Add connection",
                active_links=(
                    "workflowconnection_list",
                    "workflowconnection_add",
                    "workflowconnection_detail",
                    "workflowconnection_edit",
                ),
                auth_required=True,
            )
        )

    secret_items = []
    if secret_allowed:
        secret_items.append(
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
        secret_items.append(
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

    groups = []
    if workflow_items:
        groups.append(
            MenuGroup(
                label="Workflows",
                items=tuple(workflow_items),
            )
        )
    if secret_items:
        groups.append(
            MenuGroup(
                label="Secrets",
                items=tuple(secret_items),
            )
        )

    return (
        Menu(
            label="Automation",
            icon_class="mdi mdi-graph-outline",
            auth_required=True,
            groups=tuple(groups),
        ),
    )
