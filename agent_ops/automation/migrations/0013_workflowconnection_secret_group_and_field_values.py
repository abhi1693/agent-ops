import django.db.models.deletion
from django.db import migrations, models


def _backfill_connection_secret_fields(apps, schema_editor):
    WorkflowConnection = apps.get_model("automation", "WorkflowConnection")

    for connection in WorkflowConnection.objects.select_related("credential_secret", "credential_secret__secret_group"):
        changed = False

        if connection.secret_group_id is None and connection.credential_secret_id:
            connection.secret_group_id = connection.credential_secret.secret_group_id
            changed = True

        field_values = dict(connection.field_values or {})

        if connection.connection_type in {"openai.api", "prometheus.api", "elasticsearch.api"}:
            if "base_url" not in field_values:
                base_url = (connection.auth_config or {}).get("base_url") or (connection.metadata or {}).get("base_url")
                if base_url not in (None, ""):
                    field_values["base_url"] = base_url
                    changed = True

        if connection.credential_secret_id and connection.secret_group_id:
            secret_ref = {
                "source": "secret",
                "secret_name": connection.credential_secret.name,
            }
            field_key = {
                "openai.api": "api_key",
                "prometheus.api": "bearer_token",
                "elasticsearch.api": "auth_token",
                "github.oauth2": "webhook_secret",
            }.get(connection.connection_type)
            if field_key and field_key not in field_values:
                field_values[field_key] = secret_ref
                changed = True

        if changed:
            connection.field_values = field_values
            connection.save(update_fields=["secret_group", "field_values"])


def _noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ("automation", "0012_alter_workflowconnection_connection_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="workflowconnection",
            name="field_values",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="workflowconnection",
            name="secret_group",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="workflow_connections_by_group",
                to="automation.secretgroup",
            ),
        ),
        migrations.RunPython(_backfill_connection_secret_fields, _noop_reverse),
    ]
