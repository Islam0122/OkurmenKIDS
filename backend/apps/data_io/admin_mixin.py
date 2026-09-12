"""Drop this mixin onto any ModelAdmin to get the full Export/Import
Template UX (config page, saved templates, download-a-blank-file,
upload/preview/commit) driven by one registered ``ModelAdapter`` — no
per-model view code required beyond setting ``io_adapter_key``.
"""
from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse

from apps.users.import_export.formats import UnsupportedFileFormat

from .forms import GenericImportForm
from .models import ExportTemplate
from .registry import get_adapter
from .services import ImportValidationError, build_import_template_file, commit_import, preview_import, render_export


class TemplatedIOAdminMixin:
    """``io_adapter_key`` must be set by the subclass to a registered
    ``ModelAdapter.key`` (e.g. ``"academy.course"``). The subclass is also
    responsible for adding ``"export_selected_csv"`` to its own ``actions``
    and pointing ``change_list_template`` at a template that extends
    ``admin/data_io/change_list_toolbar.html`` (see the Course/Subject
    templates for the two-line pattern).
    """

    io_adapter_key: str = ""

    def _adapter(self):
        return get_adapter(self.io_adapter_key)

    def _url_name(self, suffix: str) -> str:
        opts = self.model._meta
        return f"{opts.app_label}_{opts.model_name}_{suffix}"

    def _changelist_queryset(self, request):
        # ChangeList treats every unrecognized GET param as a field lookup,
        # so our own params (format/template, not real filters) have to be
        # stripped before it builds the queryset or it 500s trying to filter
        # by a field that doesn't exist.
        original_get = request.GET
        request.GET = original_get.copy()
        request.GET.pop("format", None)
        request.GET.pop("template", None)
        try:
            changelist = self.get_changelist_instance(request)
            return changelist.get_queryset(request)
        finally:
            request.GET = original_get

    def get_urls(self):
        custom_urls = [
            path("io/export/", self.admin_site.admin_view(self.io_export_view), name=self._url_name("io_export")),
            path(
                "io/export/download/",
                self.admin_site.admin_view(self.io_export_download_view),
                name=self._url_name("io_export_download"),
            ),
            path("io/import/", self.admin_site.admin_view(self.io_import_view), name=self._url_name("io_import")),
            path(
                "io/import/template/",
                self.admin_site.admin_view(self.io_import_template_view),
                name=self._url_name("io_import_template"),
            ),
        ]
        return custom_urls + super().get_urls()

    # -- export -------------------------------------------------------

    def export_selected_csv(self, request, queryset):
        adapter = self._adapter()
        return render_export(adapter, adapter.prepare_queryset(queryset), adapter.default_columns(), "csv")

    export_selected_csv.short_description = "Экспортировать выбранные (CSV, стандартные поля)"

    def io_export_view(self, request):
        adapter = self._adapter()
        templates = ExportTemplate.objects.filter(model_key=adapter.key).order_by("name")
        context = {
            **self.admin_site.each_context(request),
            "title": f"Экспорт: {adapter.label}",
            "opts": self.model._meta,
            "adapter": adapter,
            "templates": templates,
            "download_url": reverse(f"admin:{self._url_name('io_export_download')}"),
            "changelist_url": reverse(f"admin:{self._url_name('changelist')}"),
            "manage_templates_url": (
                reverse("admin:data_io_exporttemplate_changelist") + f"?model_key={adapter.key}"
            ),
            "create_template_url": (
                reverse("admin:data_io_exporttemplate_builder") + f"?model_key={adapter.key}"
            ),
            "preserved_params": list(request.GET.items()),
        }
        return render(request, "admin/data_io/export.html", context)

    def io_export_download_view(self, request):
        adapter = self._adapter()
        fmt = request.GET.get("format", "csv")
        template_id = request.GET.get("template")
        if template_id:
            template = get_object_or_404(ExportTemplate, pk=template_id, model_key=adapter.key)
            columns = template.columns
        else:
            columns = adapter.default_columns()

        queryset = adapter.prepare_queryset(self._changelist_queryset(request))
        try:
            return render_export(adapter, queryset, columns, fmt)
        except UnsupportedFileFormat as exc:
            self.message_user(request, str(exc), messages.ERROR)
            return redirect(f"admin:{self._url_name('io_export')}")

    # -- import -------------------------------------------------------

    def io_import_template_view(self, request):
        adapter = self._adapter()
        fmt = request.GET.get("format", "csv")
        try:
            return build_import_template_file(adapter, fmt)
        except UnsupportedFileFormat as exc:
            self.message_user(request, str(exc), messages.ERROR)
            return redirect(f"admin:{self._url_name('io_import')}")

    def io_import_view(self, request):
        adapter = self._adapter()
        preview = None
        failed = False

        if request.method == "POST":
            form = GenericImportForm(request.POST, request.FILES)
            if form.is_valid():
                file_obj = form.cleaned_data["file"]
                if "preview" in request.POST:
                    try:
                        preview = preview_import(adapter, file_obj)
                    except UnsupportedFileFormat as exc:
                        messages.error(request, str(exc))
                else:
                    try:
                        result = commit_import(adapter, file_obj)
                    except UnsupportedFileFormat as exc:
                        messages.error(request, str(exc))
                    except ImportValidationError as exc:
                        preview = exc.preview
                        failed = True
                    else:
                        messages.success(
                            request,
                            f"Импорт завершён: создано {result.created}, обновлено {result.updated} "
                            f"из {result.total}.",
                        )
                        return redirect(f"admin:{self._url_name('changelist')}")
        else:
            form = GenericImportForm()

        context = {
            **self.admin_site.each_context(request),
            "title": f"Импорт: {adapter.label}",
            "opts": self.model._meta,
            "adapter": adapter,
            "form": form,
            "preview": preview,
            "failed": failed,
            "template_csv_url": reverse(f"admin:{self._url_name('io_import_template')}") + "?format=csv",
            "template_xlsx_url": reverse(f"admin:{self._url_name('io_import_template')}") + "?format=xlsx",
            "changelist_url": reverse(f"admin:{self._url_name('changelist')}"),
        }
        return render(request, "admin/data_io/import.html", context)
