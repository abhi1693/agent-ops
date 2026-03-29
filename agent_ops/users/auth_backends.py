from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

from .models import User


class UsernameOrEmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = username or kwargs.get(User.USERNAME_FIELD)
        if identifier is None or password is None:
            return None

        candidates = list(
            User.objects.filter(Q(username__iexact=identifier) | Q(email__iexact=identifier)).order_by("id")
        )
        if not candidates:
            User().set_password(password)
            return None

        exact_username = next((user for user in candidates if user.username.lower() == identifier.lower()), None)
        ordered_candidates = [exact_username] if exact_username else []
        ordered_candidates.extend(user for user in candidates if user is not exact_username)

        for user in ordered_candidates:
            if user.check_password(password) and self.user_can_authenticate(user):
                return user

        return None
