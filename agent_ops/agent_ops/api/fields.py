from rest_framework.relations import PrimaryKeyRelatedField


class SerializedPKRelatedField(PrimaryKeyRelatedField):
    """
    Read a related field as a nested object while still accepting primary keys on write.
    """

    def __init__(self, serializer, **kwargs):
        self.serializer = serializer
        super().__init__(**kwargs)

    def use_pk_only_optimization(self):
        return False

    def to_representation(self, value):
        return self.serializer(value, context=self.context).data

    def get_choices(self, cutoff=None):
        queryset = self.get_queryset()
        if queryset is None:
            return {}

        if cutoff is not None:
            queryset = queryset[:cutoff]

        return {
            PrimaryKeyRelatedField.to_representation(self, item): self.display_value(item)
            for item in queryset
        }
