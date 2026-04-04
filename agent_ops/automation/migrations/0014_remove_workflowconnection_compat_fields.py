from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("automation", "0013_workflowconnection_secret_group_and_field_values"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="workflowconnection",
            name="auth_config",
        ),
        migrations.RemoveField(
            model_name="workflowconnection",
            name="credential_secret",
        ),
    ]
