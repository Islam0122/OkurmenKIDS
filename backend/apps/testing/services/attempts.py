"""Taking a test: join a running session, get the attempt's questions,
submit answers, see the result.

Built on the existing models and their rules — TestSession's state machine
(``accepts_answers``), its per-session attempt limit
(``can_student_attempt``), StudentAttempt.finish() — plus the test's own
settings (publication, dates, attempts, time limit, shuffling).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import (
    Answer,
    AttemptStatus,
    Question,
    QuestionType,
    SessionStatus,
    StudentAttempt,
    TestSession,
    normalize_session_key,
)
from .grading import AttemptScore, attempt_score, check_answer

# A submit that arrives just after the deadline (network, the auto-submit
# timer itself) is still accepted.
SUBMIT_GRACE = timedelta(seconds=90)


class AttemptError(ValidationError):
    """A student-facing reason the action can't be done."""


# ---------------------------------------------------------------------------
# Joining
# ---------------------------------------------------------------------------

def find_session(key: str) -> TestSession:
    try:
        return TestSession.objects.select_related("test", "group").get(key=normalize_session_key(key))
    except TestSession.DoesNotExist:
        raise AttemptError("Сессия с таким ключом не найдена. Проверьте ключ у преподавателя.")


def session_error(session: TestSession) -> str | None:
    status = session.effective_status
    if status == SessionStatus.CREATED:
        return "Сессия ещё не запущена. Дождитесь сигнала преподавателя."
    if status == SessionStatus.PAUSED:
        return "Сессия на паузе. Дождитесь, пока преподаватель её продолжит."
    if status in TestSession.ENDED_STATUSES:
        return "Сессия уже завершена."
    return session.test.availability_error()


def _attempts_used(test, student=None, student_name: str = "") -> int:
    attempts = StudentAttempt.objects.filter(session__test=test).exclude(status=AttemptStatus.EXPIRED)
    if student is not None:
        return attempts.filter(student=student).count()
    return attempts.filter(student__isnull=True, student_name=student_name).count()


def join(session: TestSession, student_name: str = "", student=None) -> StudentAttempt:
    """Start an attempt (or return the student's unfinished one)."""
    student_name = (student_name or "").strip()
    if student is None and not student_name:
        raise AttemptError("Введите имя и фамилию.")
    error = session_error(session)
    if error:
        raise AttemptError(error)
    test = session.test
    if not test.questions.exists():
        raise AttemptError("В тесте пока нет вопросов.")

    mine = session.attempts.filter(status=AttemptStatus.ACTIVE)
    mine = mine.filter(student=student) if student is not None else mine.filter(student__isnull=True, student_name=student_name)
    current = mine.first()
    if current is not None:
        if attempt_deadline(current) and timezone.now() > attempt_deadline(current) + SUBMIT_GRACE:
            current.expire()
        else:
            return current

    limit = test.effective_max_attempts
    if limit is not None and _attempts_used(test, student, student_name) >= limit:
        raise AttemptError("Вы уже использовали все попытки для этого теста.")
    if not session.can_student_attempt(student_name=student_name, student=student):
        raise AttemptError("Лимит попыток в этой сессии исчерпан.")

    with transaction.atomic():
        attempt = StudentAttempt.objects.create(session=session, student=student, student_name=student_name)
        attempt.question_ids = pick_question_ids(test, seed=attempt.pk.int)
        attempt.save(update_fields=["question_ids"])
    return attempt


def pick_question_ids(test, seed: int) -> list[str]:
    """The attempt's questions: all (or a random ``questions_per_attempt``)
    in the test's order, shuffled when the test says so. Seeded by the
    attempt, so a reload shows the same set in the same order."""
    ids = [str(pk) for pk in test.questions.order_by("order", "created_at").values_list("pk", flat=True)]
    rng = random.Random(seed)
    if test.questions_per_attempt and test.questions_per_attempt < len(ids):
        chosen = set(rng.sample(ids, test.questions_per_attempt))
        ids = [i for i in ids if i in chosen]
    if test.shuffle_questions:
        rng.shuffle(ids)
    return ids


# ---------------------------------------------------------------------------
# Taking
# ---------------------------------------------------------------------------

def attempt_deadline(attempt: StudentAttempt):
    """When the attempt must be submitted: the test's time limit from the
    attempt start, capped by the session's own deadline. None = no limit."""
    deadlines = []
    limit = attempt.session.test.time_limit_minutes
    if limit:
        deadlines.append(attempt.started_at + timedelta(minutes=limit))
    if attempt.session.expires_at and not attempt.session.is_training:
        deadlines.append(attempt.session.expires_at)
    return min(deadlines) if deadlines else None


def ordered_questions(test, question_ids: list[str], *, shuffle_seed: int | None = None) -> list[Question]:
    """Questions in the given order, each with ``display_options`` (shuffled
    with ``shuffle_seed`` when the test shuffles options)."""
    by_id = {
        str(q.pk): q
        for q in Question.objects.filter(test=test, pk__in=question_ids).prefetch_related("options")
    }
    questions = [by_id[i] for i in question_ids if i in by_id]
    rng = random.Random(shuffle_seed)
    for question in questions:
        options = sorted(question.options.all(), key=lambda o: (o.order, str(o.pk)))
        if test.shuffle_options and shuffle_seed is not None:
            rng.shuffle(options)
        question.display_options = options
    return questions


def attempt_questions(attempt: StudentAttempt) -> list[Question]:
    return ordered_questions(attempt.session.test, attempt.question_ids, shuffle_seed=attempt.pk.int)


@dataclass
class SubmittedAnswer:
    text: str = ""
    options: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.text.strip() and not any(self.options)


def submit(attempt: StudentAttempt, answers: dict[str, SubmittedAnswer], *, timed_out: bool = False) -> AttemptScore:
    """Grade and store the answers, finish the attempt, return its score."""
    if attempt.status != AttemptStatus.ACTIVE:
        raise AttemptError("Эта попытка уже завершена.")
    now = timezone.now()
    session = attempt.session
    if session.effective_status == SessionStatus.PAUSED:
        raise AttemptError("Сессия на паузе — ответы можно отправить после продолжения.")
    ended_at = session.ended_at or session.expires_at
    if session.effective_status in TestSession.ENDED_STATUSES and ended_at and now > ended_at + SUBMIT_GRACE:
        attempt.expire()
        raise AttemptError("Сессия завершена — ответы больше не принимаются.")
    deadline = attempt_deadline(attempt)
    if deadline and now > deadline + SUBMIT_GRACE:
        attempt.expire()
        raise AttemptError("Время на прохождение теста истекло.")

    questions = attempt_questions(attempt)
    if not timed_out:
        missing = [
            str(number) for number, q in enumerate(questions, start=1)
            if q.is_required and answers.get(str(q.pk), SubmittedAnswer()).is_empty
        ]
        if missing:
            raise AttemptError(f"Ответьте на обязательные вопросы: {', '.join(missing)}.")

    with transaction.atomic():
        for question in questions:
            given = answers.get(str(question.pk))
            if given is None or given.is_empty:
                continue
            valid_ids = {str(o.pk) for o in question.display_options}
            options = [o for o in given.options if o in valid_ids]
            if question.question_type == QuestionType.SINGLE_CHOICE:
                options = options[:1]
            is_correct, grading_status = check_answer(question, given.text, options)
            Answer.objects.update_or_create(
                attempt=attempt,
                question=question,
                defaults={
                    "answer_text": given.text if question.question_type in (QuestionType.TEXT, QuestionType.CODE) else "",
                    "selected_options": options,
                    "is_correct": is_correct,
                    "grading_status": grading_status,
                },
            )
        attempt.finish()
    return attempt_score(attempt)


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

def result_rows(attempt: StudentAttempt) -> list[dict]:
    """One row per question of the attempt: the given answer, correctness
    and (for the page to show or hide) the correct answer."""
    answers = {str(a.question_id): a for a in attempt.answers.all()}
    rows = []
    for number, question in enumerate(attempt_questions(attempt), start=1):
        answer = answers.get(str(question.pk))
        option_text = {str(o.pk): o.text for o in question.display_options}
        rows.append({
            "number": number,
            "question": question,
            "answer": answer,
            "selected": [option_text[i] for i in (answer.selected_options if answer else []) if i in option_text],
            "correct_options": [o.text for o in question.display_options if o.is_correct],
            "status": _row_status(answer),
        })
    return rows


def _row_status(answer) -> str:
    if answer is None:
        return "skipped"
    if answer.is_correct is None:
        return "pending"
    return "correct" if answer.is_correct else "wrong"


def is_passed(attempt: StudentAttempt, score: AttemptScore | None = None) -> bool | None:
    """None while answers are still waiting for review."""
    score = score or attempt_score(attempt)
    if score.pending:
        return None
    return score.percent >= attempt.session.test.passing_score
