import django_tables2 as tables
from django.utils.html import format_html

from core.tables import AgentOpsTable
from users.models import Group, ObjectPermission, Token, User


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

    class Meta(AgentOpsTable.Meta):
        model = User
        fields = ("username", "email", "display_name", "is_staff", "is_active")
        default_columns = ("username", "email", "display_name", "is_staff", "is_active")

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

    class Meta(AgentOpsTable.Meta):
        model = Group
        fields = (
            "name",
            "description",
            "user_count",
            "permission_count",
            "object_permission_count",
        )
        default_columns = (
            "name",
            "description",
            "user_count",
            "permission_count",
            "object_permission_count",
        )

    def render_description(self, value):
        return value or "-"


class ObjectPermissionTable(AgentOpsTable):
    name = tables.Column(linkify=True)
    actions = tables.Column()
    content_type_count = tables.Column(verbose_name="Content types")
    enabled = tables.Column()

    class Meta(AgentOpsTable.Meta):
        model = ObjectPermission
        fields = ("name", "actions", "content_type_count", "enabled")
        default_columns = ("name", "actions", "content_type_count", "enabled")

    def render_actions(self, value):
        return ", ".join(value) if value else "-"

    def render_enabled(self, value):
        return _render_boolean_badge(value)


class TokenTable(AgentOpsTable):
    masked_key = tables.Column(verbose_name="Identifier")
    description = tables.Column()
    is_active = tables.Column(verbose_name="Status")
    created = tables.DateTimeColumn()
    expires = tables.DateTimeColumn()
    write_enabled = tables.Column(verbose_name="Write")
    actions = tables.TemplateColumn(
        template_code='<a class="btn btn-danger btn-sm" href="{% url \'token_delete\' record.pk %}">Delete</a>',
        verbose_name="",
        orderable=False,
        attrs={"td": {"class": "text-end"}},
    )

    class Meta(AgentOpsTable.Meta):
        model = Token
        fields = (
            "masked_key",
            "description",
            "is_active",
            "created",
            "expires",
            "write_enabled",
            "actions",
        )
        default_columns = (
            "masked_key",
            "description",
            "is_active",
            "created",
            "expires",
            "write_enabled",
            "actions",
        )

    def render_description(self, value):
        return value or "-"

    def render_is_active(self, value):
        badge_class = "text-bg-success" if value else "text-bg-secondary"
        label = "Active" if value else "Inactive"
        return format_html('<span class="badge {}">{}</span>', badge_class, label)

    def render_expires(self, value):
        return value or "Never"

    def render_write_enabled(self, value):
        return "Enabled" if value else "Read only"
