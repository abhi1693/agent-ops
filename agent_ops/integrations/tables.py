import django_tables2 as tables

from core.tables import AgentOpsTable, RowActionsColumn
from integrations.models import Secret


class SecretTable(AgentOpsTable):
    name = tables.Column(linkify=True)
    provider = tables.Column(verbose_name="Provider")
    organization = tables.Column(linkify=True)
    workspace = tables.Column(linkify=True)
    environment = tables.Column(linkify=True)
    enabled = tables.Column()
    actions = RowActionsColumn(actions=("edit", "delete"))

    class Meta(AgentOpsTable.Meta):
        model = Secret
        fields = ("name", "provider", "organization", "workspace", "environment", "enabled", "actions")
        default_columns = ("name", "provider", "organization", "workspace", "environment", "enabled", "actions")

    def render_provider(self, value, record):
        return record.get_provider_display()

    def render_organization(self, value):
        return value or "-"

    def render_workspace(self, value):
        return value or "-"

    def render_environment(self, value):
        return value or "-"
