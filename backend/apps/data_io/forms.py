from django import forms


class GenericImportForm(forms.Form):
    file = forms.FileField(
        label="Файл (CSV или XLSX)",
        widget=forms.ClearableFileInput(attrs={"class": "ok-input"}),
    )
