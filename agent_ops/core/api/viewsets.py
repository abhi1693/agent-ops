from agent_ops.api.permissions import TokenPermissions
from agent_ops.api.viewsets import ReadOnlyModelViewSet
from core.changelog import restrict_objectchange_queryset
from core.filtersets import ObjectChangeFilterSet
from core.models import ObjectChange

from .serializers import ObjectChangeSerializer


class ObjectChangeViewSet(ReadOnlyModelViewSet):
    queryset = ObjectChange.objects.select_related(
        "user",
        "changed_object_type",
        "related_object_type",
    ).order_by("-time")
    serializer_class = ObjectChangeSerializer
    filterset_class = ObjectChangeFilterSet
    ordering_fields = ("time", "action", "user_name", "request_id")
    permission_classes = [TokenPermissions]

    def get_queryset(self):
        return restrict_objectchange_queryset(
            super().get_queryset(),
            request=self.request,
        )
