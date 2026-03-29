import django_tables2 as tables
from django.utils.html import format_html

from core.tables import AgentOpsTable, RowActionsColumn
from users.models import Group, Membership, ObjectPermission, Token, User


def _render_boolean_badge(value):
    badge_class = "text-bg-success" if value else "text-bg-secondary"
    label = "Yes" if value else "No"
    return format_html('<span class="badge {}">{}</span>', badge_class, label)


class UserTable(AgentOpsTable):
    username = tables.Column(linkify=True)
    email = tables.Column()
    display_name = tables.Column(verbose_name="Display name")
    is_staff = tables.Column(verbose_name="Staff")
    is_active = tables.Column(verbose_name="Active")
    actions = RowActionsColumn(actions=("edit", "delete"))

    class Meta(AgentOpsTable.Meta):
        model = User
        fields = ("username", "email", "display_name", "is_staff", "is_active", "actions")
        default_columns = ("username", "email", "display_name", "is_staff", "is_active", "actions")

    def render_display_name(self, value):
        return value or "-"

    def render_is_staff(self, value):
        return _render_boolean_badge(value)

    def render_is_active(self, value):
        return _render_boolean_badge(value)


class GroupTable(AgentOpsTable):
    name = tables.Column(linkify=True)
    description = tables.Column()
    user_count = tables.Column(verbose_name="Members")
    permission_count = tables.Column(verbose_name="Auth permissions")
    object_permission_count = tables.Column(verbose_name="Object permissions")
    actions = RowActionsColumn(actions=("edit", "delete"))

    class Meta(AgentOpsTable.Meta):
        model = Group
        fields = (
            "name",
            "description",
            "user_count",
            "permission_count",
            "object_permission_count",
            "actions",
        )
        default_columns = (
            "name",
            "description",
            "user_count",
            "permission_count",
            "object_permission_count",
            "actions",
        )

    def render_description(self, value):
        return value or "-"


class ObjectPermissionTable(AgentOpsTable):
    name = tables.Column(linkify=True)
    action_list = tables.Column(accessor="actions", verbose_name="Actions")
    content_type_count = tables.Column(verbose_name="Content types")
    enabled = tables.Column()
    actions = RowActionsColumn(actions=("edit", "delete"))

    class Meta(AgentOpsTable.Meta):
        model = ObjectPermission
        fields = ("name", "action_list", "content_type_count", "enabled", "actions")
        default_columns = ("name", "action_list", "content_type_count", "enabled", "actions")

    def render_action_list(self, value):
        return ", ".join(value) if value else "-"

    def render_enabled(self, value):
        return _render_boolean_badge(value)


class MembershipTable(AgentOpsTable):
    user = tables.Column(linkify=lambda record: record.user.get_absolute_url())
    scope_label = tables.Column(verbose_name="Scope", linkify=True)
    scope_type = tables.Column(verbose_name="Scope type")
    is_default = tables.Column(verbose_name="Default")
    is_active = tables.Column(verbose_name="Active")
    group_count = tables.Column(verbose_name="Groups")
    object_permission_count = tables.Column(verbose_name="Object permissions")
    actions = RowActionsColumn(actions=("edit", "delete"))

    class Meta(AgentOpsTable.Meta):
        model = Membership
        fields = (
            "user",
            "scope_label",
            "scope_type",
            "is_default",
            "is_active",
            "group_count",
            "object_permission_count",
            "actions",
        )
        default_columns = (
            "user",
            "scope_label",
            "scope_type",
            "is_default",
            "is_active",
            "group_count",
            "object_permission_count",
            "actions",
        )

    def render_is_default(self, value):
        return _render_boolean_badge(value)

    def render_is_active(self, value):
        return _render_boolean_badge(value)


class TokenTable(AgentOpsTable):
    masked_key = tables.Column(verbose_name="Identifier")
    description = tables.Column()
    scope_membership = tables.Column(verbose_name="Scope")
    is_active = tables.Column(verbose_name="Status")
    created = tables.DateTimeColumn()
    expires = tables.DateTimeColumn()
    write_enabled = tables.Column(verbose_name="Write")
    actions = RowActionsColumn(actions=("delete",))

    class Meta(AgentOpsTable.Meta):
        model = Token
        fields = (
            "masked_key",
            "description",
            "scope_membership",
            "is_active",
            "created",
            "expires",
            "write_enabled",
            "actions",
        )
        default_columns = (
            "masked_key",
            "description",
            "scope_membership",
            "is_active",
            "created",
            "expires",
            "write_enabled",
            "actions",
        )

    def render_description(self, value):
        return value or "-"

    def render_scope_membership(self, value):
        return value.scope_label if value else "Default scope"

    def render_is_active(self, value):
        badge_class = "text-bg-success" if value else "text-bg-secondary"
        label = "Active" if value else "Inactive"
        return format_html('<span class="badge {}">{}</span>', badge_class, label)

    def render_expires(self, value):
        return value or "Never"

    def render_write_enabled(self, value):
        return "Enabled" if value else "Read only"
