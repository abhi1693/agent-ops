import django_tables2 as tables

from automation.models import Workflow, WorkflowConnection
from core.tables import AgentOpsTable, RowActionsColumn


class WorkflowTable(AgentOpsTable):
    name = tables.Column(linkify=True)
    organization = tables.Column(linkify=True)
    workspace = tables.Column(linkify=True)
    environment = tables.Column(linkify=True)
    node_count = tables.Column(verbose_name="Nodes")
    edge_count = tables.Column(verbose_name="Edges")
    enabled = tables.Column()
    actions = RowActionsColumn(actions=("edit", "delete"))

    class Meta(AgentOpsTable.Meta):
        model = Workflow
        fields = (
            "name",
            "organization",
            "workspace",
            "environment",
            "node_count",
            "edge_count",
            "enabled",
            "actions",
        )
        default_columns = fields

    def render_organization(self, value):
        return value or "-"

    def render_workspace(self, value):
        return value or "-"

    def render_environment(self, value):
        return value or "-"


class WorkflowConnectionTable(AgentOpsTable):
    name = tables.Column(linkify=True)
    integration_id = tables.Column(verbose_name="Integration")
    connection_type = tables.Column(verbose_name="Credential Type")
    organization = tables.Column(linkify=True)
    workspace = tables.Column(linkify=True)
    environment = tables.Column(linkify=True)
    enabled = tables.Column()
    actions = RowActionsColumn(actions=("edit", "delete"))

    class Meta(AgentOpsTable.Meta):
        model = WorkflowConnection
        fields = (
            "name",
            "integration_id",
            "connection_type",
            "organization",
            "workspace",
            "environment",
            "enabled",
            "actions",
        )
        default_columns = fields

    def render_organization(self, value):
        return value or "-"

    def render_workspace(self, value):
        return value or "-"

    def render_environment(self, value):
        return value or "-"
