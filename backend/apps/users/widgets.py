from __future__ import annotations

from django import forms


class PhotoPreviewWidget(forms.ClearableFileInput):
    """ClearableFileInput with a custom template only — same name/id/checkbox
    wiring Django's own widget uses (see get_context() there), so the form
    still saves/clears the file exactly as before. Only the markup changes.
    """

    template_name = "admin/users/widgets/photo_preview.html"
