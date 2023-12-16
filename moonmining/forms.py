"""Forms."""

from django import forms


class MoonScanForm(forms.Form):
    """A form for moon scanning."""

    scan = forms.CharField(widget=forms.Textarea)
