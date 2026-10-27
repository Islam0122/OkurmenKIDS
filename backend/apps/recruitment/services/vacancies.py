"""Жизненный цикл вакансии.

    черновик ─► опубликована ⇄ приостановлена
        │            │              │
        └──────────► закрыта ◄──────┘ ─► архив ─► закрыта (восстановить)
                       │
                       └─► опубликована (открыть снова)

* Публикует только HR явным действием; при публикации проверяется, что у
  вакансии заполнено всё, что увидит посетитель.
* Дата публикации — момент первой публикации после черновика или повторного
  открытия закрытой вакансии; возобновление после паузы её не меняет.
* Закрытие и архив не трогают отклики, собеседования и историю.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from ..models import HRActivity, Vacancy
from . import activity
from .common import RecruitmentError

V = Vacancy.Status

TRANSITIONS: dict[str, set[str]] = {
    V.DRAFT: {V.PUBLISHED, V.CLOSED},
    V.PUBLISHED: {V.PAUSED, V.CLOSED},
    V.PAUSED: {V.PUBLISHED, V.CLOSED},
    V.CLOSED: {V.PUBLISHED, V.ARCHIVED},
    V.ARCHIVED: {V.CLOSED},
}

# На эти вакансии HR может добавлять кандидатов вручную.
ACCEPTS_CANDIDATES = {V.DRAFT, V.PUBLISHED, V.PAUSED}

# Что должно быть заполнено, чтобы вакансию можно было показать на сайте.
REQUIRED_FOR_PUBLISHING = {
    "title": "название",
    "description": "описание",
    "responsibilities": "обязанности",
    "requirements": "требования",
    "location": "место работы",
}


def allowed(vacancy: Vacancy) -> list[str]:
    return [value for value, _ in V.choices if value in TRANSITIONS.get(vacancy.status, set())]


def missing_for_publishing(vacancy: Vacancy) -> list[str]:
    missing = [label for field, label in REQUIRED_FOR_PUBLISHING.items() if not (getattr(vacancy, field) or "").strip()]
    if vacancy.closes_on and vacancy.closes_on < timezone.localdate():
        missing.append("срок приёма откликов (дата уже прошла)")
    return missing


@transaction.atomic
def change_status(vacancy: Vacancy, new_status: str, actor) -> Vacancy:
    vacancy = Vacancy.objects.select_for_update().get(pk=vacancy.pk)
    old = vacancy.status
    if new_status == old:
        return vacancy
    if new_status not in TRANSITIONS.get(old, set()):
        raise RecruitmentError(
            f"Из статуса «{V(old).label}» нельзя перейти в «{V(new_status).label}».", "invalid_transition",
            extra={"allowed": allowed(vacancy)},
        )
    now = timezone.now()
    if new_status == V.PUBLISHED:
        missing = missing_for_publishing(vacancy)
        if missing:
            raise RecruitmentError("Чтобы опубликовать вакансию, заполните: " + ", ".join(missing) + ".",
                                   "incomplete", extra={"missing": missing})
        if old in (V.DRAFT, V.CLOSED) or vacancy.published_at is None:
            vacancy.published_at = now
        vacancy.closed_at = None
    elif new_status == V.CLOSED:
        vacancy.closed_at = vacancy.closed_at if old == V.ARCHIVED else now
        vacancy.archived_at = None
    elif new_status == V.ARCHIVED:
        vacancy.archived_at = now
    vacancy.status = new_status
    vacancy.save(update_fields=["status", "published_at", "closed_at", "archived_at", "updated_at"])
    activity.log(HRActivity.Kind.VACANCY_STATUS, actor, vacancy=vacancy, from_status=old, to_status=new_status,
                 message=f"{vacancy.title}: {V(old).label} → {V(new_status).label}")
    return vacancy
