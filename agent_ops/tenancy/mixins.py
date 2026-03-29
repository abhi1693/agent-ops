from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

from users.scopes import get_request_actor_scope


class StaffOrScopedUserRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    raise_exception = True

    def test_func(self):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return True
        return get_request_actor_scope(self.request) is not None
