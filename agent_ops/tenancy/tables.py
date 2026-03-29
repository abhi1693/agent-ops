import django_tables2 as tables

from core.tables import AgentOpsTable, RowActionsColumn
from tenancy.models import Environment, Organization, Workspace


class OrganizationTable(AgentOpsTable):
    name = tables.Column(linkify=True)
    description = tables.Column()
    workspace_count = tables.Column(verbose_name="Workspaces")
    environment_count = tables.Column(verbose_name="Environments")
    actions = RowActionsColumn(actions=("edit", "delete"))

    class Meta(AgentOpsTable.Meta):
        model = Organization
        fields = ("name", "description", "workspace_count", "environment_count", "actions")
        default_columns = ("name", "description", "workspace_count", "environment_count", "actions")

    def render_description(self, value):
        return value or "-"


class WorkspaceTable(AgentOpsTable):
    name = tables.Column(linkify=True)
    organization = tables.Column(linkify=True)
    description = tables.Column()
    environment_count = tables.Column(verbose_name="Environments")
    actions = RowActionsColumn(actions=("edit", "delete"))

    class Meta(AgentOpsTable.Meta):
        model = Workspace
        fields = ("name", "organization", "description", "environment_count", "actions")
        default_columns = ("name", "organization", "description", "environment_count", "actions")

    def render_description(self, value):
        return value or "-"


class EnvironmentTable(AgentOpsTable):
    name = tables.Column(linkify=True)
    workspace = tables.Column(linkify=True)
    organization = tables.Column(linkify=True)
    description = tables.Column()
    actions = RowActionsColumn(actions=("edit", "delete"))

    class Meta(AgentOpsTable.Meta):
        model = Environment
        fields = ("name", "workspace", "organization", "description", "actions")
        default_columns = ("name", "workspace", "organization", "description", "actions")

    def render_description(self, value):
        return value or "-"
