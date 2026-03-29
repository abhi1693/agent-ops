from rest_framework import serializers

from users.models import Group, User


class UserSerializer(serializers.HyperlinkedModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="api:users-api:user-detail")

    class Meta:
        model = User
        fields = (
            "id",
            "url",
            "username",
            "display_name",
            "first_name",
            "last_name",
            "email",
            "is_staff",
            "is_active",
            "date_joined",
            "last_login",
        )


class GroupSerializer(serializers.HyperlinkedModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="api:users-api:group-detail")

    class Meta:
        model = Group
        fields = (
            "id",
            "url",
            "name",
            "description",
        )
