from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("automation", "0008_workflowrun_async_queue_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="workflowrun",
            name="scheduler_state",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
