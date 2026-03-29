from rest_framework.viewsets import ReadOnlyModelViewSet

from users import filtersets
from users.models import Group, User

from .serializers import GroupSerializer, UserSerializer


class UserViewSet(ReadOnlyModelViewSet):
    queryset = User.objects.all().order_by("username")
    serializer_class = UserSerializer
    filterset_class = filtersets.UserFilterSet
    ordering_fields = ("username", "email", "date_joined", "last_login")


class GroupViewSet(ReadOnlyModelViewSet):
    queryset = Group.objects.all().order_by("name")
    serializer_class = GroupSerializer
    filterset_class = filtersets.GroupFilterSet
    ordering_fields = ("name",)
