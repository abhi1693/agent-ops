import uuid

from django.conf import settings
from django.db import migrations, models


def populate_workflow_run_job_ids(apps, schema_editor):
    WorkflowRun = apps.get_model("automation", "WorkflowRun")
    for run in WorkflowRun.objects.filter(job_id__isnull=True).iterator():
        run.job_id = uuid.uuid4()
        run.save(update_fields=("job_id",))


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("automation", "0007_workflowversion_workflowsteprun_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="workflowrun",
            name="trigger_metadata",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="workflowrun",
            name="execution_mode",
            field=models.CharField(
                choices=[
                    ("workflow", "Workflow"),
                    ("node_path", "Node path"),
                    ("node_preview", "Node preview"),
                ],
                default="workflow",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="workflowrun",
            name="target_node_id",
            field=models.CharField(blank=True, default="", max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="workflowrun",
            name="requested_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="workflowrun",
            name="queue_name",
            field=models.CharField(blank=True, default="", max_length=100),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="workflowrun",
            name="job_id",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.RunPython(populate_workflow_run_job_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="workflowrun",
            name="job_id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AddIndex(
            model_name="workflowrun",
            index=models.Index(fields=["status", "execution_mode"], name="automation__status_1ea218_idx"),
        ),
    ]
