from functools import cached_property

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.serializers import as_serializer_error
from rest_framework.utils.serializer_helpers import BindingDict


class BaseModelSerializer(serializers.HyperlinkedModelSerializer):
    def __init__(self, *args, nested=False, fields=None, **kwargs):
        self.nested = nested
        self._requested_fields = fields

        if self.nested and not fields:
            self._requested_fields = getattr(self.Meta, "brief_fields", None)

        super().__init__(*args, **kwargs)

        if self.nested:
            self.validators = []

    @cached_property
    def fields(self):
        if not self._requested_fields:
            return super().fields

        fields = BindingDict(self)
        for key, value in self.get_fields().items():
            if key in self._requested_fields:
                fields[key] = value
        return fields


class ValidatedModelSerializer(BaseModelSerializer):
    def get_unique_together_constraints(self, model):
        return []

    def validate(self, data):
        if self.nested:
            return data

        attrs = data.copy()
        opts = self.Meta.model._meta

        for field in [*opts.local_many_to_many, *opts.related_objects]:
            attrs.pop(field.name, None)

        if self.instance is None:
            instance = self.Meta.model(**attrs)
        else:
            instance = self.instance
            for key, value in attrs.items():
                setattr(instance, key, value)

        try:
            instance.full_clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(as_serializer_error(exc)) from exc

        return data
