from django import forms
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

from users.models import Group, ObjectPermission, Token, User
from users.preferences import THEME_CHOICES
from .auth import apply_standard_widget_classes


class BaseUserForm(forms.ModelForm):
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"size": 8}),
    )
    object_permissions = forms.ModelMultipleChoiceField(
        queryset=ObjectPermission.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"size": 8}),
    )

    class Meta:
        model = User
        fields = (
            "username",
            "email",
            "first_name",
            "last_name",
            "display_name",
            "is_active",
            "is_staff",
            "is_superuser",
            "groups",
            "object_permissions",
            "user_permissions",
        )
        widgets = {
            "user_permissions": forms.SelectMultiple(attrs={"size": 8}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["groups"].queryset = Group.objects.order_by("name")
        self.fields["object_permissions"].queryset = ObjectPermission.objects.order_by("name")
        self.fields["user_permissions"].queryset = Permission.objects.order_by(
            "content_type__app_label", "content_type__model", "codename"
        )
        apply_standard_widget_classes(self)


class UserCreateForm(BaseUserForm):
    password1 = forms.CharField(widget=forms.PasswordInput, label="Password")
    password2 = forms.CharField(widget=forms.PasswordInput, label="Confirm password")

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if not password1 or not password2:
            raise forms.ValidationError("Password fields are required.")
        if password1 != password2:
            raise forms.ValidationError("The two password fields didn’t match.")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
            self.save_m2m()
        return user


class UserUpdateForm(BaseUserForm):
    password1 = forms.CharField(widget=forms.PasswordInput, required=False, label="New password")
    password2 = forms.CharField(widget=forms.PasswordInput, required=False, label="Confirm new password")

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 or password2:
            if not password1 or not password2:
                raise forms.ValidationError("Enter the new password twice to change it.")
            if password1 != password2:
                raise forms.ValidationError("The two password fields didn’t match.")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("password1")
        if password:
            user.set_password(password)
        if commit:
            user.save()
            self.save_m2m()
        return user


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("email", "first_name", "last_name", "display_name")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_standard_widget_classes(self)


class GroupForm(forms.ModelForm):
    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"size": 8}),
    )
    object_permissions = forms.ModelMultipleChoiceField(
        queryset=ObjectPermission.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"size": 8}),
    )

    class Meta:
        model = Group
        fields = ("name", "description", "permissions", "object_permissions")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["permissions"].queryset = Permission.objects.order_by(
            "content_type__app_label", "content_type__model", "codename"
        )
        self.fields["object_permissions"].queryset = ObjectPermission.objects.order_by("name")
        apply_standard_widget_classes(self)


class ObjectPermissionForm(forms.ModelForm):
    content_types = forms.ModelMultipleChoiceField(
        queryset=ContentType.objects.none(),
        widget=forms.SelectMultiple(attrs={"size": 8}),
    )
    actions = forms.MultipleChoiceField(
        choices=ObjectPermission.ActionChoices.choices,
        widget=forms.CheckboxSelectMultiple,
    )
    constraints = forms.JSONField(required=False, widget=forms.Textarea(attrs={"rows": 8}))

    class Meta:
        model = ObjectPermission
        fields = ("name", "description", "enabled", "content_types", "actions", "constraints")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["content_types"].queryset = ContentType.objects.order_by("app_label", "model")
        self.initial.setdefault("actions", self.instance.actions if self.instance.pk else ["view"])
        apply_standard_widget_classes(self)

    def clean_constraints(self):
        return self.cleaned_data["constraints"] or None


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
