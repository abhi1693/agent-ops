from django import forms
from django.contrib.auth.forms import AuthenticationForm

from core.form_widgets import apply_standard_widget_classes
from users.models import Token, User
from users.preferences import THEME_CHOICES


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        max_length=254,
        label="Username or email",
        widget=forms.TextInput(
            attrs={
                "autofocus": True,
                "autocomplete": "username",
                "placeholder": "Username or email",
            }
        ),
    )
    password = forms.CharField(
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "placeholder": "Password",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_standard_widget_classes(self)


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("email", "first_name", "last_name", "display_name")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_standard_widget_classes(self)


class TokenCreateForm(forms.ModelForm):
    class Meta:
        model = Token
        fields = ("description", "expires", "enabled", "write_enabled")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_standard_widget_classes(self)


class UserPreferenceForm(forms.Form):
    theme = forms.ChoiceField(choices=THEME_CHOICES)
    page_size = forms.IntegerField(min_value=10, max_value=250)
    landing_page = forms.CharField(max_length=200)

    def __init__(self, *args, config, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = config
        self.fields["theme"].initial = config.get("ui.theme")
        self.fields["page_size"].initial = config.get("ui.page_size")
        self.fields["landing_page"].initial = config.get("ui.landing_page")
        apply_standard_widget_classes(self)

    def save(self):
        self.config.set("ui.theme", self.cleaned_data["theme"])
        self.config.set("ui.page_size", self.cleaned_data["page_size"])
        self.config.set("ui.landing_page", self.cleaned_data["landing_page"])
        self.config.save()
        return self.config

