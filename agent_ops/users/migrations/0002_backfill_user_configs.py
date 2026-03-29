from django.db import migrations


def backfill_user_configs(apps, schema_editor):
    User = apps.get_model("users", "User")
    UserConfig = apps.get_model("users", "UserConfig")

    existing_user_ids = set(UserConfig.objects.values_list("user_id", flat=True))
    missing_configs = [
        UserConfig(user_id=user_id)
        for user_id in User.objects.exclude(pk__in=existing_user_ids).values_list("pk", flat=True)
    ]
    if missing_configs:
        UserConfig.objects.bulk_create(missing_configs)


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(backfill_user_configs, migrations.RunPython.noop),
    ]
