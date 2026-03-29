from django.db import models

from users.preferences import DEFAULT_USER_PREFERENCES


def _flatten_dict(value, prefix=""):
    flattened = {}
    for key, nested_value in value.items():
        nested_key = f"{prefix}.{key}" if prefix else key
        if isinstance(nested_value, dict):
            flattened.update(_flatten_dict(nested_value, nested_key))
        else:
            flattened[nested_key] = nested_value
    return flattened


def _resolve_path(data, keys):
    current = data
    for key in keys:
        current = current[key]
    return current


class UserConfig(models.Model):
    user = models.OneToOneField(
        "users.User",
        on_delete=models.CASCADE,
        related_name="config",
    )
    data = models.JSONField(default=dict)

    class Meta:
        ordering = ("user",)
        verbose_name = "user preferences"
        verbose_name_plural = "user preferences"

    def __str__(self) -> str:
        return f"Preferences for {self.user}"

    def get(self, path, default=None):
        keys = path.split(".")
        for source in (self.data, DEFAULT_USER_PREFERENCES):
            try:
                return _resolve_path(source, keys)
            except (KeyError, TypeError):
                continue
        return default

    def all(self):
        return _flatten_dict(self.data)

    def set(self, path, value, commit=False):
        current = self.data
        keys = path.split(".")
        for index, key in enumerate(keys[:-1]):
            if key in current and not isinstance(current[key], dict):
                err_path = ".".join(keys[: index + 1])
                raise TypeError(f"Key '{err_path}' is a leaf node; cannot assign new keys")
            current = current.setdefault(key, {})

        leaf_key = keys[-1]
        if leaf_key in current and isinstance(current[leaf_key], dict) and not isinstance(value, dict):
            raise TypeError(f"Key '{path}' is a dictionary; cannot assign a non-dictionary value")
        if leaf_key in current and isinstance(current[leaf_key], dict) and isinstance(value, dict):
            current[leaf_key].update(value)
        else:
            current[leaf_key] = value

        if commit:
            self.save()

    set.alters_data = True

    def clear(self, path, commit=False):
        current = self.data
        keys = path.split(".")
        for key in keys[:-1]:
            if key not in current or not isinstance(current[key], dict):
                if commit:
                    self.save()
                return
            current = current[key]
        current.pop(keys[-1], None)
        if commit:
            self.save()

    clear.alters_data = True
