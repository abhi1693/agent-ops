from django import forms
from django.contrib.auth.forms import AuthenticationForm


def _merge_widget_class(widget, class_name):
    current = widget.attrs.get("class", "")
    classes = [part for part in current.split() if part]
    if class_name not in classes:
        classes.append(class_name)
    widget.attrs["class"] = " ".join(classes)


def apply_standard_widget_classes(form):
    for field in form.fields.values():
        widget = field.widget

        if isinstance(widget, forms.HiddenInput):
            continue
        if isinstance(widget, forms.CheckboxInput):
            _merge_widget_class(widget, "form-check-input")
            continue
        if isinstance(widget, forms.CheckboxSelectMultiple):
            _merge_widget_class(widget, "form-check-input")
            continue
        if isinstance(widget, (forms.Select, forms.SelectMultiple)):
            _merge_widget_class(widget, "form-select")
            continue
        if isinstance(widget, forms.Textarea):
            _merge_widget_class(widget, "form-control")
            continue

        _merge_widget_class(widget, "form-control")


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
