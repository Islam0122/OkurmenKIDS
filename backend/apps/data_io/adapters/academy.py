"""Course / CourseLessonPlan adapters — the curriculum catalogue.

Upsert keys:
- Course: ``name`` (the model's own unique field).
- CourseLessonPlan: ``course`` + ``lesson_number`` + ``subject``. A row
  matching an existing plan on all three updates that plan in place (same
  primary key); otherwise a new plan is created. The model's own unique
  constraint is the narrower pair (``course``, ``lesson_number``), so a row
  whose pair is already taken by a plan of *another* subject is rejected
  instead of silently re-assigning that plan's subject. The import is
  partial: such rows (and any other invalid row) are skipped and reported,
  the rest are saved.

Both adapters build an in-memory model instance from the parsed row and
call ``full_clean()`` on it rather than re-implementing the model's own
rules (lesson_number <= course.count_lesson, subject must belong to the
course, the uniqueness constraints) — one source of truth for that logic,
shared with the API serializers and the admin forms.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, QuerySet

from apps.academy.models import Course, CourseLessonPlan
from apps.users.models import Subject

from ..registry import FieldSpec, ModelAdapter, register
from ..validation import flatten_validation_error, parse_int, parse_url_list

# ---------------------------------------------------------------------------
# Course
# ---------------------------------------------------------------------------


def _course_prepare_queryset(queryset: QuerySet[Course]) -> QuerySet[Course]:
    return queryset.prefetch_related("subjects").annotate(
        _lesson_plans_count=Count("lesson_plans", distinct=True),
        _groups_count=Count("groups", distinct=True),
    )


def _course_lesson_plans_count(obj: Course) -> int:
    value = getattr(obj, "_lesson_plans_count", None)
    return value if value is not None else obj.lesson_plans.count()


def _course_groups_count(obj: Course) -> int:
    value = getattr(obj, "_groups_count", None)
    return value if value is not None else obj.groups.count()


COURSE_FIELDS = [
    FieldSpec("id", "ID", lambda o: o.id),
    FieldSpec("name", "Название курса", lambda o: o.name, importable=True, required=True),
    FieldSpec("description", "Описание", lambda o: o.description, importable=True),
    FieldSpec(
        "count_lesson",
        "Количество занятий",
        lambda o: o.count_lesson,
        importable=True,
        required=True,
        help_text="Целое число, минимум 1.",
    ),
    FieldSpec(
        "subjects",
        "Предметы",
        lambda o: "; ".join(s.name for s in o.subjects.all()),
        importable=True,
        help_text='Список названий предметов через ";". Пусто — курс останется без предметов.',
    ),
    FieldSpec("lesson_plans_count", "Планов занятий создано", _course_lesson_plans_count),
    FieldSpec("groups_count", "Групп на курсе", _course_groups_count),
    FieldSpec("created_at", "Дата создания", lambda o: o.created_at.isoformat()),
    FieldSpec("updated_at", "Дата обновления", lambda o: o.updated_at.isoformat()),
]


def _validate_course_row(row_number: int, raw: dict[str, str], seen: dict):
    errors: list[str] = []

    name = (raw.get("name") or "").strip()
    description = (raw.get("description") or "").strip()
    count_lesson_raw = (raw.get("count_lesson") or "").strip()
    subjects_raw = (raw.get("subjects") or "").strip()

    if not name:
        errors.append("Поле «Название курса» обязательно.")

    count_lesson = None
    if not count_lesson_raw:
        errors.append("Поле «Количество занятий» обязательно.")
    else:
        count_lesson, error = parse_int(count_lesson_raw, field_label="Количество занятий", min_value=1)
        if error:
            errors.append(error)

    subjects: list[Subject] = []
    if subjects_raw:
        for part in [p.strip() for p in subjects_raw.split(";") if p.strip()]:
            subject = Subject.objects.filter(name__iexact=part).first()
            if subject is None:
                errors.append(f'Предмет "{part}" не найден.')
            else:
                subjects.append(subject)

    if name:
        seen_names = seen.setdefault("names", {})
        key = name.lower()
        if key in seen_names:
            errors.append(f"Дублирующееся название «{name}» в файле (строка {seen_names[key]}).")
        else:
            seen_names[key] = row_number

    if errors:
        return None, errors

    existing = Course.objects.filter(name__iexact=name).first()
    instance = existing or Course()
    instance.name = name
    instance.description = description
    instance.count_lesson = count_lesson

    try:
        instance.full_clean(exclude=["subjects"])
    except DjangoValidationError as exc:
        return None, flatten_validation_error(exc)

    return {"instance": instance, "subjects": subjects}, []


def _apply_course_row(clean: dict):
    instance: Course = clean["instance"]
    created = instance.pk is None
    instance.save()
    instance.subjects.set(clean["subjects"])
    return instance, created


COURSE_ADAPTER = ModelAdapter(
    key="academy.course",
    label="Курсы",
    fields=COURSE_FIELDS,
    prepare_queryset=_course_prepare_queryset,
    validate_row=_validate_course_row,
    apply_row=_apply_course_row,
    default_fields=[
        "id",
        "name",
        "description",
        "count_lesson",
        "lesson_plans_count",
        "subjects",
        "groups_count",
        "created_at",
        "updated_at",
    ],
    import_notes=(
        "Курс ищется по названию (обновляется существующий, иначе создаётся новый). "
        "Колонка «Предметы» — список названий через «;»; если оставить пустой, "
        "у курса не останется предметов."
    ),
)

register(COURSE_ADAPTER)


# ---------------------------------------------------------------------------
# CourseLessonPlan
# ---------------------------------------------------------------------------


def _lesson_plan_prepare_queryset(queryset: QuerySet[CourseLessonPlan]) -> QuerySet[CourseLessonPlan]:
    return queryset.select_related("course", "subject")


LESSON_PLAN_FIELDS = [
    FieldSpec("id", "ID", lambda o: o.id),
    FieldSpec("course", "Курс", lambda o: o.course.name, importable=True, required=True),
    FieldSpec("lesson_number", "Номер занятия", lambda o: o.lesson_number, importable=True, required=True),
    FieldSpec("subject", "Предмет", lambda o: o.subject.name, importable=True, required=True),
    FieldSpec("topic", "Тема занятия", lambda o: o.topic, importable=True, required=True),
    FieldSpec("description", "Описание", lambda o: o.description, importable=True),
    FieldSpec("youtube_url", "Ссылка на YouTube", lambda o: o.youtube_url, importable=True),
    FieldSpec(
        "presentation_urls",
        "Ссылки на презентации",
        lambda o: "; ".join(o.presentation_urls or []),
        importable=True,
        help_text='Список ссылок через ";".',
    ),
    FieldSpec("homework_title", "Домашнее задание", lambda o: o.homework_title, importable=True),
    FieldSpec("homework_description", "Описание домашнего задания", lambda o: o.homework_description, importable=True),
    FieldSpec("created_at", "Дата создания", lambda o: o.created_at.isoformat()),
    FieldSpec("updated_at", "Дата обновления", lambda o: o.updated_at.isoformat()),
]


def _validate_lesson_plan_row(row_number: int, raw: dict[str, str], seen: dict):
    errors: list[str] = []

    course_name = (raw.get("course") or "").strip()
    lesson_number_raw = (raw.get("lesson_number") or "").strip()
    subject_name = (raw.get("subject") or "").strip()
    topic = (raw.get("topic") or "").strip()
    description = (raw.get("description") or "").strip()
    youtube_url = (raw.get("youtube_url") or "").strip()
    presentation_urls_raw = (raw.get("presentation_urls") or "").strip()
    homework_title = (raw.get("homework_title") or "").strip()
    homework_description = (raw.get("homework_description") or "").strip()

    course = None
    if not course_name:
        errors.append("Поле «Курс» обязательно.")
    else:
        course = Course.objects.filter(name__iexact=course_name).first()
        if course is None:
            errors.append(f'Курс "{course_name}" не найден.')

    lesson_number = None
    if not lesson_number_raw:
        errors.append("Поле «Номер занятия» обязательно.")
    else:
        lesson_number, error = parse_int(lesson_number_raw, field_label="Номер занятия", min_value=1)
        if error:
            errors.append(error)

    subject = None
    if not subject_name:
        errors.append("Поле «Предмет» обязательно.")
    else:
        subject = Subject.objects.filter(name__iexact=subject_name).first()
        if subject is None:
            errors.append(f'Предмет "{subject_name}" не найден.')

    if not topic:
        errors.append("Поле «Тема занятия» обязательно.")

    presentation_urls: list[str] = []
    if presentation_urls_raw:
        presentation_urls, url_errors = parse_url_list(presentation_urls_raw, field_label="Ссылки на презентации")
        errors.extend(url_errors)

    # Keyed on the pair, not the full (course, lesson_number, subject) key:
    # two rows sharing the pair can never both be saved (unique constraint),
    # whatever their subjects. The first one wins, later ones are reported.
    if course is not None and lesson_number is not None:
        seen_pairs = seen.setdefault("pairs", {})
        pair_key = (course.pk, lesson_number)
        if pair_key in seen_pairs:
            errors.append(
                f"Занятие №{lesson_number} курса «{course.name}» уже есть в файле "
                f"(строка {seen_pairs[pair_key]}) — повторная строка пропущена."
            )
        else:
            seen_pairs[pair_key] = row_number

    if errors:
        return None, errors

    existing = CourseLessonPlan.objects.filter(course=course, lesson_number=lesson_number, subject=subject).first()
    if existing is None:
        taken = (
            CourseLessonPlan.objects.filter(course=course, lesson_number=lesson_number)
            .select_related("subject")
            .first()
        )
        if taken is not None:
            return None, [
                f"Занятие №{lesson_number} курса «{course.name}» уже существует с предметом "
                f"«{taken.subject.name}» (ID {taken.pk}), а в файле указан «{subject.name}». "
                "Импорт не меняет предмет существующего плана — исправьте предмет в файле "
                "или в карточке плана."
            ]
    instance = existing or CourseLessonPlan()
    instance.course = course
    instance.lesson_number = lesson_number
    instance.subject = subject
    instance.topic = topic
    instance.description = description
    instance.youtube_url = youtube_url
    instance.presentation_urls = presentation_urls
    instance.homework_title = homework_title
    instance.homework_description = homework_description

    try:
        instance.full_clean()
    except DjangoValidationError as exc:
        return None, flatten_validation_error(exc)

    return {"instance": instance}, []


def _apply_lesson_plan_row(clean: dict):
    instance: CourseLessonPlan = clean["instance"]
    created = instance.pk is None
    instance.save()
    return instance, created


LESSON_PLAN_ADAPTER = ModelAdapter(
    key="academy.courselessonplan",
    label="Планы занятий",
    fields=LESSON_PLAN_FIELDS,
    prepare_queryset=_lesson_plan_prepare_queryset,
    validate_row=_validate_lesson_plan_row,
    apply_row=_apply_lesson_plan_row,
    partial_import=True,
    default_fields=[
        "id",
        "course",
        "lesson_number",
        "subject",
        "topic",
        "description",
        "youtube_url",
        "presentation_urls",
        "homework_title",
        "homework_description",
        "created_at",
        "updated_at",
    ],
    import_notes=(
        "План ищется по «Курс + Номер занятия + Предмет»: найденный план обновляется "
        "(его ID не меняется), иначе создаётся новый. Импорт ничего не удаляет и не "
        "создаёт реальные занятия. Курс и Предмет ищутся по названию — предмет обязательно "
        "должен входить в состав указанного курса, а номер занятия не может превышать "
        "количество занятий курса. Строки с ошибками пропускаются, остальные сохраняются."
    ),
)

register(LESSON_PLAN_ADAPTER)
