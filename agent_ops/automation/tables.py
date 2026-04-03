import django_tables2 as tables

from automation.models import Secret, SecretGroup, Workflow, WorkflowConnection
from core.tables import AgentOpsTable, RowActionsColumn


class SecretTable(AgentOpsTable):
    name = tables.Column(linkify=True)
    secret_group = tables.Column(linkify=True, verbose_name="Secret Group")
    provider = tables.Column(verbose_name="Provider")
    organization = tables.Column(linkify=True)
    workspace = tables.Column(linkify=True)
    environment = tables.Column(linkify=True)
    enabled = tables.Column()
    actions = RowActionsColumn(actions=("edit", "delete"))

    class Meta(AgentOpsTable.Meta):
        model = Secret
        fields = ("name", "secret_group", "provider", "organization", "workspace", "environment", "enabled", "actions")
        default_columns = ("name", "secret_group", "provider", "organization", "workspace", "environment", "enabled", "actions")

    def render_provider(self, value, record):
        return record.get_provider_display()

    def render_organization(self, value):
        return value or "-"

    def render_workspace(self, value):
        return value or "-"

    def render_environment(self, value):
        return value or "-"


class SecretGroupTable(AgentOpsTable):
    name = tables.Column(linkify=True)
    organization = tables.Column(linkify=True)
    workspace = tables.Column(linkify=True)
    environment = tables.Column(linkify=True)
    actions = RowActionsColumn(actions=("edit", "delete"))

    class Meta(AgentOpsTable.Meta):
        model = SecretGroup
        fields = ("name", "organization", "workspace", "environment", "actions")
        default_columns = ("name", "organization", "workspace", "environment", "actions")

    def render_organization(self, value):
        return value or "-"

    def render_workspace(self, value):
        return value or "-"

    def render_environment(self, value):
        return value or "-"


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
    connection_type = tables.Column(verbose_name="Connection Type")
    credential_secret = tables.Column(linkify=True, verbose_name="Credential Secret")
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
            "credential_secret",
            "organization",
            "workspace",
            "environment",
            "enabled",
            "actions",
        )
        default_columns = fields

    def render_credential_secret(self, value):
        return value or "-"

    def render_organization(self, value):
        return value or "-"

    def render_workspace(self, value):
        return value or "-"

    def render_environment(self, value):
        return value or "-"
