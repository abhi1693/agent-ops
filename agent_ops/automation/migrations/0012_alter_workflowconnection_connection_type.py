from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("automation", "0011_workflowconnection"),
    ]

    operations = [
        migrations.AlterField(
            model_name="workflowconnection",
            name="connection_type",
            field=models.CharField(max_length=150),
        ),
    ]
