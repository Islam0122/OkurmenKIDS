"""Subject adapter.

Upsert key: ``name`` (the model's own unique field). ``teachers`` and
``courses`` are exported (they're genuinely useful to see next to a
subject) but never imported — Subject doesn't own either relation
(Teacher.subjects and Course.subjects do), so importing them here would
silently rewrite a relationship that belongs to a different model's admin.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import QuerySet

from apps.users.import_export.formats import parse_bool
from apps.users.models import Subject

from ..registry import FieldSpec, ModelAdapter, register
from ..validation import flatten_validation_error


def _subject_prepare_queryset(queryset: QuerySet[Subject]) -> QuerySet[Subject]:
    return queryset.prefetch_related("teachers__user", "courses")


def _subject_teachers(obj: Subject) -> str:
    return "; ".join(t.user.get_full_name() or t.user.username for t in obj.teachers.all())


def _subject_courses(obj: Subject) -> str:
    return "; ".join(c.name for c in obj.courses.all())


SUBJECT_FIELDS = [
    FieldSpec("id", "ID", lambda o: o.id),
    FieldSpec("name", "Название предмета", lambda o: o.name, importable=True, required=True),
    FieldSpec("description", "Описание", lambda o: o.description, importable=True),
    FieldSpec(
        "is_active",
        "Активен",
        lambda o: o.is_active,
        importable=True,
        help_text="true/false (по умолчанию — true).",
    ),
    FieldSpec("teachers", "Тренеры", _subject_teachers),
    FieldSpec("courses", "Курсы", _subject_courses),
    FieldSpec("created_at", "Дата создания", lambda o: o.created_at.isoformat()),
    FieldSpec("updated_at", "Дата обновления", lambda o: o.updated_at.isoformat()),
]


def _validate_subject_row(row_number: int, raw: dict[str, str], seen: dict):
    errors: list[str] = []

    name = (raw.get("name") or "").strip()
    description = (raw.get("description") or "").strip()
    is_active_raw = (raw.get("is_active") or "").strip()

    if not name:
        errors.append("Поле «Название предмета» обязательно.")

    try:
        is_active = parse_bool(is_active_raw, default=True)
    except ValueError:
        errors.append(f"Некорректное булево значение «Активен»: «{is_active_raw}».")
        is_active = True

    if name:
        seen_names = seen.setdefault("names", {})
        key = name.lower()
        if key in seen_names:
            errors.append(f"Дублирующееся название «{name}» в файле (строка {seen_names[key]}).")
        else:
            seen_names[key] = row_number

    if errors:
        return None, errors

    existing = Subject.objects.filter(name__iexact=name).first()
    instance = existing or Subject()
    instance.name = name
    instance.description = description
    instance.is_active = is_active

    try:
        instance.full_clean()
    except DjangoValidationError as exc:
        return None, flatten_validation_error(exc)

    return {"instance": instance}, []


def _apply_subject_row(clean: dict):
    instance: Subject = clean["instance"]
    created = instance.pk is None
    instance.save()
    return instance, created


SUBJECT_ADAPTER = ModelAdapter(
    key="users.subject",
    label="Предметы",
    fields=SUBJECT_FIELDS,
    prepare_queryset=_subject_prepare_queryset,
    validate_row=_validate_subject_row,
    apply_row=_apply_subject_row,
    default_fields=[
        "id",
        "name",
        "description",
        "is_active",
        "teachers",
        "courses",
        "created_at",
        "updated_at",
    ],
    import_notes=(
        "Предмет ищется по названию (обновляется существующий, иначе создаётся новый). "
        "Тренеры и Курсы — только для просмотра при экспорте; чтобы изменить их, "
        "редактируйте самого Тренера или Курс."
    ),
)

register(SUBJECT_ADAPTER)
