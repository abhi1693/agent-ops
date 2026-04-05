from automation.models import Workflow, WorkflowConnection
from core.navigation import Menu, MenuGroup, MenuItem
from users.restrictions import has_model_action_permission


def get_navigation_menus(request):
    workflow_allowed = has_model_action_permission(Workflow, request=request, action="view")
    workflow_connection_allowed = has_model_action_permission(WorkflowConnection, request=request, action="view")
    if not workflow_allowed and not workflow_connection_allowed:
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
                link_text="Credentials",
                icon_class="mdi mdi-connection",
                add_link=(
                    "workflowconnection_add"
                    if has_model_action_permission(WorkflowConnection, request=request, action="add")
                    else None
                ),
                add_button_label="Add credential",
                active_links=(
                    "workflowconnection_list",
                    "workflowconnection_add",
                    "workflowconnection_detail",
                    "workflowconnection_edit",
                ),
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

    return (
        Menu(
            label="Automation",
            icon_class="mdi mdi-graph-outline",
            auth_required=True,
            groups=tuple(groups),
        ),
    )
