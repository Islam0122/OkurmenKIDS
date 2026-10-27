"""Перенос данных HR-кабинета на модель «кандидат + отклик».

* Каждый существующий кандидат становится человеком (Candidate) и получает один
  отклик (Application) с прежними вакансией, этапом, источником, датой,
  ответственным и учётной записью сотрудника. Собеседования и журнал событий
  привязываются к этому отклику.
* Этап «Первичный контакт» (contacted) → «Первичный просмотр» (screening), в
  том числе в истории переходов.
* Заметки кандидата и записи «Взаимодействие с кандидатом» → внутренние
  заметки HR (InternalNote); журнал остаётся как был.
* Вакансии: «Открыта» → «Черновик». Раньше вакансии были внутренним
  справочником и на сайте не публиковались — публикует их только HR явным
  действием. «Приостановлена» и «Закрыта» сохраняются. Адрес на сайте (slug)
  строится из названия.
"""
import re
import secrets

from django.db import migrations

TRANSLIT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "ң": "n", "о": "o", "ө": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ү": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
})
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def slugify(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", text.lower().translate(TRANSLIT)).strip("-")
    return value[:80].strip("-") or "vacancy"


def digits(phone: str) -> str:
    value = re.sub(r"\D", "", phone or "")
    if len(value) == 10 and value.startswith("0"):
        value = "996" + value[1:]
    return value


def number(year: int, taken: set) -> str:
    while True:
        value = f"{year}-{''.join(secrets.choice(ALPHABET) for _ in range(6))}"
        if value not in taken:
            taken.add(value)
            return value


def forward(apps, schema_editor):
    Vacancy = apps.get_model("recruitment", "Vacancy")
    Candidate = apps.get_model("recruitment", "Candidate")
    Application = apps.get_model("recruitment", "Application")
    Interview = apps.get_model("recruitment", "Interview")
    HRActivity = apps.get_model("recruitment", "HRActivity")
    InternalNote = apps.get_model("recruitment", "InternalNote")

    used = set()
    for vacancy in Vacancy.objects.order_by("id"):
        base = slugify(vacancy.title)
        slug = f"{base}-{vacancy.pk}"
        while slug in used:
            slug = f"{slug}-x"
        used.add(slug)
        vacancy.slug = slug
        if vacancy.status == "open":
            vacancy.status = "draft"
        if vacancy.status == "closed" and vacancy.closed_at is None:
            vacancy.closed_at = vacancy.updated_at
        vacancy.save(update_fields=["slug", "status", "closed_at"])

    taken = set(Application.objects.values_list("number", flat=True))
    for candidate in Candidate.objects.order_by("id"):
        status = "screening" if candidate.status == "contacted" else candidate.status
        application = Application.objects.create(
            number=number(candidate.created_at.year, taken), candidate=candidate, vacancy_id=candidate.vacancy_id,
            position=candidate.position, channel="hr", source=candidate.source,
            source_details=candidate.source_details, applied_on=candidate.added_on,
            responsible_id=candidate.responsible_id, status=status, status_changed_at=candidate.status_changed_at,
            hired_user_id=candidate.hired_user_id, created_by_id=candidate.created_by_id,
            created_at=candidate.created_at,
        )
        candidate.phone_digits = digits(candidate.phone)
        candidate.email = (candidate.email or "").strip().lower()
        candidate.save(update_fields=["phone_digits", "email"])
        Interview.objects.filter(candidate_id=candidate.pk).update(application=application)
        HRActivity.objects.filter(candidate_id=candidate.pk).update(application=application)
        if candidate.notes.strip():
            InternalNote.objects.create(candidate=candidate, application=application, author_id=candidate.created_by_id,
                                        text=candidate.notes.strip(), created_at=candidate.created_at)
        for entry in HRActivity.objects.filter(candidate_id=candidate.pk, kind="candidate_note"):
            InternalNote.objects.create(candidate=candidate, application=application, author_id=entry.actor_id,
                                        text=entry.message, created_at=entry.created_at)

    HRActivity.objects.filter(from_status="contacted").update(from_status="screening")
    HRActivity.objects.filter(to_status="contacted").update(to_status="screening")


class Migration(migrations.Migration):

    dependencies = [
        ("recruitment", "0002_careers_schema"),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
