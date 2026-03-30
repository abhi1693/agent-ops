from automation.models import Workflow
from core.navigation import Menu, MenuGroup, MenuItem
from users.restrictions import has_model_action_permission


def get_navigation_menus(request):
    workflow_allowed = has_model_action_permission(Workflow, request=request, action="view")
    if not workflow_allowed:
        return ()

    return (
        Menu(
            label="Automation",
            icon_class="mdi mdi-graph-outline",
            auth_required=True,
            groups=(
                MenuGroup(
                    label="Workflows",
                    items=(
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
                        ),
                    ),
                ),
            ),
        ),
    )

