from __future__ import annotations

from django.contrib import admin, messages
from django.db import IntegrityError
from django.db.models import QuerySet
from django.http import HttpRequest
from django.shortcuts import redirect, render
from django.urls import path, reverse

from .models import ExportTemplate
from .registry import get_adapter


@admin.register(ExportTemplate)
class ExportTemplateAdmin(admin.ModelAdmin):
    """Standard Django admin list/delete for saved templates; Create/Edit are
    handled by a dedicated field-picker view (``builder_view``) instead of
    the normal add/change form — a JSONField of columns has no usable
    default widget, and the builder gives a real checkbox/label/order table
    per adapter field instead.
    """

    list_display = ("name", "section_label", "fmt", "columns_count", "created_by", "updated_at")
    list_filter = ("model_key", "fmt")
    search_fields = ("name",)
    ordering = ("model_key", "name")
    actions = ["duplicate_templates"]

    @admin.display(description="Раздел", ordering="model_key")
    def section_label(self, obj: ExportTemplate) -> str:
        try:
            return get_adapter(obj.model_key).label
        except KeyError:
            return obj.model_key

    @admin.display(description="Колонок")
    def columns_count(self, obj: ExportTemplate) -> int:
        return len(obj.columns or [])

    @admin.action(description="Дублировать выбранные шаблоны")
    def duplicate_templates(self, request: HttpRequest, queryset: QuerySet[ExportTemplate]):
        created = 0
        for template in queryset:
            base_name = f"{template.name} (копия)"
            name = base_name
            suffix = 1
            while ExportTemplate.objects.filter(model_key=template.model_key, name=name).exists():
                suffix += 1
                name = f"{base_name} {suffix}"
            ExportTemplate.objects.create(
                model_key=template.model_key,
                name=name,
                columns=template.columns,
                fmt=template.fmt,
                created_by=request.user,
            )
            created += 1
        self.message_user(request, f"Продублировано шаблонов: {created}.")

    def get_urls(self):
        custom_urls = [
            path(
                "builder/",
                self.admin_site.admin_view(self.builder_view),
                name="data_io_exporttemplate_builder",
            ),
        ]
        return custom_urls + super().get_urls()

    def add_view(self, request, form_url="", extra_context=None):
        url = reverse("admin:data_io_exporttemplate_builder")
        model_key = request.GET.get("model_key", "")
        if model_key:
            url += f"?model_key={model_key}"
        return redirect(url)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        return redirect(reverse("admin:data_io_exporttemplate_builder") + f"?id={object_id}")

    def builder_view(self, request: HttpRequest):
        template_id = request.GET.get("id") or request.POST.get("id")
        template = None
        if template_id:
            template = ExportTemplate.objects.filter(pk=template_id).first()
            if template is None:
                self.message_user(request, "Шаблон не найден.", messages.ERROR)
                return redirect(reverse("admin:data_io_exporttemplate_changelist"))

        model_key = request.POST.get("model_key") or (template.model_key if template else request.GET.get("model_key"))
        try:
            adapter = get_adapter(model_key)
        except KeyError:
            self.message_user(request, "Неизвестный раздел для шаблона.", messages.ERROR)
            return redirect(reverse("admin:data_io_exporttemplate_changelist"))

        existing_columns = {c["field"]: c for c in (template.columns if template else [])}
        included_order = list(existing_columns.keys())

        error = None
        name_value = template.name if template else ""
        fmt_value = template.fmt if template else ExportTemplate.Format.CSV

        if request.method == "POST":
            name_value = request.POST.get("name", "").strip()
            fmt_value = request.POST.get("fmt", ExportTemplate.Format.CSV)

            selected: list[tuple[int, int, str, str]] = []
            for position, field in enumerate(adapter.fields):
                if not request.POST.get(f"include__{field.key}"):
                    continue
                label = (request.POST.get(f"label__{field.key}") or "").strip() or field.label
                try:
                    order = int(request.POST.get(f"order__{field.key}", position))
                except ValueError:
                    order = position
                selected.append((order, position, field.key, label))
            selected.sort(key=lambda row: (row[0], row[1]))
            columns = [{"field": key, "label": label} for _order, _pos, key, label in selected]

            if not name_value:
                error = "Укажите название шаблона."
            elif not columns:
                error = "Выберите хотя бы одно поле для экспорта."
            else:
                try:
                    if template:
                        template.name = name_value
                        template.columns = columns
                        template.fmt = fmt_value
                        template.save()
                    else:
                        template = ExportTemplate.objects.create(
                            model_key=model_key,
                            name=name_value,
                            columns=columns,
                            fmt=fmt_value,
                            created_by=request.user,
                        )
                except IntegrityError:
                    error = f'Шаблон с названием «{name_value}» уже существует для раздела «{adapter.label}».'
                else:
                    self.message_user(request, f'Шаблон «{template.name}» сохранён.', messages.SUCCESS)
                    return redirect(reverse("admin:data_io_exporttemplate_changelist") + f"?model_key={model_key}")

            # Save failed (IntegrityError) or validation failed — re-render the
            # form reflecting exactly what the user just submitted, not the
            # template's previous saved state.
            if error:
                included_order = [key for _o, _p, key, _l in selected]
                existing_columns = {c["field"]: c for c in columns}

        field_rows = []
        for position, field in enumerate(adapter.fields):
            existing = existing_columns.get(field.key)
            field_rows.append(
                {
                    "key": field.key,
                    "spec_label": field.label,
                    "help_text": field.help_text,
                    "included": existing is not None,
                    "label": (existing or {}).get("label", field.label),
                    "order": included_order.index(field.key) if field.key in included_order else position,
                }
            )

        context = {
            **self.admin_site.each_context(request),
            "title": (f"Редактировать шаблон: {template.name}" if template else f"Новый шаблон: {adapter.label}"),
            "opts": self.model._meta,
            "adapter": adapter,
            "template": template,
            "field_rows": field_rows,
            "name_value": name_value,
            "fmt_value": fmt_value,
            "error": error,
            "changelist_url": reverse("admin:data_io_exporttemplate_changelist") + f"?model_key={model_key}",
        }
        return render(request, "admin/data_io/template_builder.html", context)
