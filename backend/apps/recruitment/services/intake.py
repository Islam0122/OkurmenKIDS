"""Поступление откликов и учёт людей.

Отклик с сайта (`submit_public`):

* Повторная отправка той же формы (тот же `submission_token`) возвращает уже
  созданную заявку, а не вторую.
* Действующий отклик с теми же email или телефоном на эту же вакансию —
  отказ «Вы уже откликнулись» (409).
* Кандидат ищется по контактам, никогда по имени. Совпали и email, и телефон с
  одним кандидатом — отклик привязывается к нему (его профиль не
  перезаписывается, заполняются только пустые поля). Совпало только одно из
  двух — создаётся новый кандидат, а отклик помечается «Проверить на дубль»:
  связать записи HR решает сам (`merge`).
* Учётная запись LMS не создаётся.

HR вручную (`create_by_hr`): при совпадении контактов сервер не создаёт
кандидата молча, а возвращает найденные совпадения (409) — HR выбирает
существующего кандидата или подтверждает, что это другой человек.

Удаление персональных данных (`erase`) — по запросу кандидата или по сроку
хранения (`manage.py purge_candidate_data`): ФИО, контакты, анкета, письмо,
резюме и заметки стираются, а сами отклики, этапы и даты остаются для
отчётов. Данные принятого сотрудника и кандидата с действующим откликом не
удаляются.
"""
from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Max, Q, QuerySet
from django.utils import timezone

from ..models import Application, Candidate, HRActivity, InternalNote, Vacancy
from . import activity, files
from .common import RecruitmentError, new_application_number, normalize_email, phone_digits, split_full_name
from .pipeline import S, TERMINAL

PROFILE_FIELDS = ("city", "experience", "education", "skills", "portfolio_url")
ERASED_NAME = "Данные удалены"


def find_matches(email: str, digits: str, exclude: int | None = None) -> QuerySet:
    """Действующие кандидаты с тем же email или телефоном (имя не учитывается)."""
    q = Q()
    if email:
        q |= Q(email=email)
    if digits:
        q |= Q(phone_digits=digits)
    if not q:
        return Candidate.objects.none()
    qs = Candidate.objects.filter(q, merged_into__isnull=True, erased_at__isnull=True)
    return qs.exclude(pk=exclude) if exclude else qs


def match_brief(candidate: Candidate, email: str, digits: str) -> dict:
    return {
        "id": candidate.pk, "full_name": candidate.full_name, "email": candidate.email, "phone": candidate.phone,
        "same_email": bool(email) and candidate.email == email,
        "same_phone": bool(digits) and candidate.phone_digits == digits,
        "applications": candidate.applications.count(),
    }


def _fill_blanks(candidate: Candidate, data: dict) -> None:
    changed = [f for f in PROFILE_FIELDS if data.get(f) and not getattr(candidate, f)]
    for f in changed:
        setattr(candidate, f, data[f])
    if changed:
        candidate.save(update_fields=[*changed, "updated_at"])


def _active_on_vacancy(vacancy: Vacancy, email: str, digits: str) -> bool:
    q = Q()
    if email:
        q |= Q(candidate__email=email)
    if digits:
        q |= Q(candidate__phone_digits=digits)
    return Application.objects.filter(q, vacancy=vacancy).exclude(status__in=TERMINAL).exists()


def already_applied() -> RecruitmentError:
    return RecruitmentError("Вы уже откликнулись на эту вакансию — заявка у нас, HR свяжется с вами.",
                            "already_applied", status=409)


@transaction.atomic
def submit_public(vacancy: Vacancy, data: dict, resume=None) -> tuple[Application, bool]:
    """Отклик посетителя сайта. Возвращает (заявка, создана ли сейчас)."""
    token = data["submission_token"]
    existing = Application.objects.filter(submission_token=token).first()
    if existing is not None:
        if existing.vacancy_id != vacancy.pk:
            raise RecruitmentError("Форма уже отправлена. Обновите страницу.", "token_reused", status=409)
        return existing, False
    # Отклики на одну вакансию — по очереди: два одинаковых запроса не создадут двух заявок.
    vacancy = Vacancy.objects.select_for_update().get(pk=vacancy.pk)
    if not vacancy.is_accepting:
        raise RecruitmentError("Вакансия больше не принимает отклики.", "vacancy_closed", status=410)
    email = normalize_email(data["email"])
    digits = phone_digits(data["phone"])
    if _active_on_vacancy(vacancy, email, digits):
        raise already_applied()
    if resume is not None:
        files.validate_resume(resume)

    profile = {f: data.get(f, "") for f in PROFILE_FIELDS}
    matches = list(find_matches(email, digits))
    strong = [c for c in matches if c.email == email and c.phone_digits == digits]
    if len(strong) == 1:
        candidate, needs_review = strong[0], False
        _fill_blanks(candidate, profile)
    else:
        last, first, middle = split_full_name(data["full_name"])
        candidate = Candidate.objects.create(last_name=last, first_name=first, middle_name=middle,
                                             phone=data["phone"].strip(), phone_digits=digits, email=email, **profile)
        needs_review = bool(matches)

    now = timezone.now()
    snapshot = {"full_name": data["full_name"], "phone": data["phone"].strip(), "email": email, **profile}
    try:
        with transaction.atomic():
            application = Application.objects.create(
                number=new_application_number(), candidate=candidate, vacancy=vacancy,
                channel=Application.Channel.PUBLIC, source=data.get("source") or Application.Source.COMPANY_SITE,
                applied_on=timezone.localdate(), responsible=vacancy.responsible, status=S.NEW,
                status_changed_at=now, cover_letter=data.get("cover_letter", ""), submitted_data=snapshot,
                consent_at=now, consent_version=settings.RECRUITMENT_CONSENT_VERSION, submission_token=token,
                needs_duplicate_review=needs_review, created_at=now,
            )
    except IntegrityError as exc:
        raise already_applied() from exc
    if resume is not None:
        files.attach_resume(application, resume)
    activity.log(HRActivity.Kind.APPLICATION_RECEIVED, None, application=application, vacancy=vacancy,
                 to_status=S.NEW, message=f"Заявка {application.number} на «{vacancy.title}»"
                 + (" · контакты совпадают с другим кандидатом — проверьте" if needs_review else ""))
    # Начало истории этапов: время входа в «Новый отклик».
    activity.log(HRActivity.Kind.CANDIDATE_STATUS, None, application=application, vacancy=vacancy,
                 to_status=S.NEW, message="Отклик получен")
    return application, True


@transaction.atomic
def create_by_hr(actor, *, candidate: Candidate | None = None, person: dict | None = None,
                 confirm_new: bool = False, **app) -> Application:
    """Отклик, который HR добавляет сам (звонок, рекомендация, агентство)."""
    vacancy = app.get("vacancy")
    if vacancy is not None and vacancy.status not in ("draft", "published", "paused"):
        raise RecruitmentError("Кандидата можно добавить только на действующую вакансию.", "vacancy_closed")
    if candidate is None:
        person = dict(person or {})
        email = normalize_email(person.get("email", ""))
        digits = phone_digits(person.get("phone", ""))
        matches = list(find_matches(email, digits))
        if matches and not confirm_new:
            raise RecruitmentError(
                "Кандидат с такими контактами уже есть. Выберите его или подтвердите, что это другой человек.",
                "possible_duplicates", status=409, extra={"matches": [match_brief(c, email, digits) for c in matches]},
            )
        person["email"], person["phone_digits"] = email, digits
        candidate = Candidate.objects.create(created_by=actor, **person)
        activity.log(HRActivity.Kind.CANDIDATE_CREATED, actor, candidate=candidate, message=candidate.full_name)
    elif candidate.merged_into_id or candidate.erased_at:
        raise RecruitmentError("Эта запись кандидата закрыта (объединена или данные удалены).", "candidate_closed")
    if vacancy is not None and Application.objects.filter(candidate=candidate, vacancy=vacancy) \
            .exclude(status__in=TERMINAL).exists():
        raise RecruitmentError("У кандидата уже есть действующий отклик на эту вакансию.", "duplicate_application",
                               status=409)
    now = timezone.now()
    app.setdefault("responsible", actor)
    application = Application.objects.create(number=new_application_number(), candidate=candidate,
                                             channel=Application.Channel.HR, status=S.NEW, status_changed_at=now,
                                             created_by=actor, created_at=now, **app)
    activity.log(HRActivity.Kind.CANDIDATE_CREATED, actor, application=application, vacancy=vacancy,
                 to_status=S.NEW, message=f"Отклик {application.number}: {application.position_label or '—'}")
    activity.log(HRActivity.Kind.CANDIDATE_STATUS, actor, application=application, vacancy=vacancy,
                 to_status=S.NEW, message="Кандидат добавлен")
    return application


def update_contacts(candidate: Candidate) -> None:
    """Пересчитать нормализованные контакты после правки профиля."""
    candidate.email = normalize_email(candidate.email)
    candidate.phone_digits = phone_digits(candidate.phone)


@transaction.atomic
def merge(source: Candidate, target: Candidate, actor) -> Candidate:
    """Объединить запись-дубль `source` с `target`: отклики, заметки и история
    переходят к `target`, сама `source` остаётся (помечена `merged_into`)."""
    source = Candidate.objects.select_for_update().get(pk=source.pk)
    target = Candidate.objects.select_for_update().get(pk=target.pk)
    if source.pk == target.pk:
        raise RecruitmentError("Нельзя объединить кандидата с самим собой.", "same_candidate")
    for c in (source, target):
        if c.merged_into_id or c.erased_at:
            raise RecruitmentError("Одна из записей уже объединена или её данные удалены.", "candidate_closed")
    active_target = set(target.applications.exclude(status__in=TERMINAL).exclude(vacancy__isnull=True)
                        .values_list("vacancy_id", flat=True))
    clash = source.applications.exclude(status__in=TERMINAL).filter(vacancy_id__in=active_target)
    if clash.exists():
        raise RecruitmentError("У обеих записей есть действующие отклики на одну вакансию — сначала закройте лишний.",
                               "duplicate_application", status=409)
    if source.applications.filter(hired_user__isnull=False).exists() and \
            target.applications.filter(hired_user__isnull=False).exists():
        raise RecruitmentError("Обе записи уже связаны с учётными записями сотрудников.", "already_hired", status=409)
    moved = list(source.applications.values_list("number", flat=True))
    source.applications.update(candidate=target, needs_duplicate_review=False)
    target.applications.update(needs_duplicate_review=False)
    InternalNote.objects.filter(candidate=source).update(candidate=target)
    HRActivity.objects.filter(candidate=source).update(candidate=target)
    for f in ("last_name", "middle_name", "phone", "email", *PROFILE_FIELDS):
        if not getattr(target, f) and getattr(source, f):
            setattr(target, f, getattr(source, f))
    update_contacts(target)
    target.save()
    source.merged_into = target
    source.save(update_fields=["merged_into", "updated_at"])
    activity.log(HRActivity.Kind.CANDIDATE_MERGED, actor, candidate=target,
                 message=f"Присоединена запись «{source.full_name}» (#{source.pk}); отклики: {', '.join(moved) or '—'}")
    return target


@transaction.atomic
def dismiss_duplicate(application: Application, actor) -> Application:
    application.needs_duplicate_review = False
    application.save(update_fields=["needs_duplicate_review", "updated_at"])
    activity.log(HRActivity.Kind.CANDIDATE_UPDATED, actor, application=application,
                 message="Проверено: это другой человек, не дубль")
    return application


def _erasable(candidate: Candidate) -> None:
    if candidate.erased_at:
        raise RecruitmentError("Персональные данные уже удалены.", "already_erased")
    if candidate.merged_into_id:
        raise RecruitmentError("Запись объединена с другой — удаляйте данные у основной записи.", "candidate_closed")
    if candidate.applications.filter(hired_user__isnull=False).exists():
        raise RecruitmentError("Кандидат принят на работу: его данные хранятся как данные сотрудника.", "hired",
                               status=409)
    if candidate.applications.exclude(status__in=TERMINAL).exists():
        raise RecruitmentError("Сначала закройте действующие отклики (отказ или кандидат отказался).", "active",
                               status=409)


@transaction.atomic
def erase(candidate: Candidate, actor, reason: str = "") -> Candidate:
    candidate = Candidate.objects.select_for_update().get(pk=candidate.pk)
    _erasable(candidate)
    for merged in candidate.merged_from.all():
        _wipe(merged)
    _wipe(candidate)
    candidate.erased_at = timezone.now()
    candidate.save(update_fields=["erased_at", "updated_at"])
    activity.log(HRActivity.Kind.CANDIDATE_ERASED, actor, candidate=candidate, message=reason[:255])
    return candidate


def _wipe(candidate: Candidate) -> None:
    for application in candidate.applications.all():
        if application.resume:
            application.resume.delete(save=False)
            application.resume = ""
        application.cover_letter = ""
        application.submitted_data = {}
        application.resume_name = ""
        application.resume_size = None
        application.source_details = ""
        application.save(update_fields=["resume", "cover_letter", "submitted_data", "resume_name", "resume_size",
                                        "source_details", "updated_at"])
        application.interviews.update(notes="", strengths="", concerns="", result_comment="", cancel_reason="")
    candidate.internal_notes.update(text="[удалено]")
    candidate.activities.exclude(kind=HRActivity.Kind.CANDIDATE_STATUS).update(message="")
    for f in ("last_name", "middle_name", "phone", "phone_digits", "email", *PROFILE_FIELDS):
        setattr(candidate, f, "")
    candidate.first_name = ERASED_NAME
    candidate.save()


def retention_candidates(days: int | None = None) -> QuerySet:
    """Кандидаты без найма и без действующих откликов, по которым ничего не
    происходило дольше срока хранения."""
    days = settings.RECRUITMENT_RETENTION_DAYS if days is None else days
    border = timezone.now() - timedelta(days=days)
    return (Candidate.objects.filter(erased_at__isnull=True, merged_into__isnull=True)
            .exclude(applications__hired_user__isnull=False)
            .exclude(applications__status__in=[s for s in S.values if s not in TERMINAL])
            .annotate(last_event=Max("activities__created_at"), last_change=Max("applications__updated_at"))
            .filter(Q(last_event__lt=border) | Q(last_event__isnull=True), updated_at__lt=border)
            .filter(Q(last_change__lt=border) | Q(last_change__isnull=True)))
