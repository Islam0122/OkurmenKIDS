"""Test analytics, built only from existing data — nothing is stored twice.

    Группа (academy.Group, TestSession.group)
      → Предмет (users.Subject, via Test.subject)
        → Тест (Test)
          → Сессия (TestSession)
            → Студенты (SessionParticipant roster / StudentAttempt.student)
              → Попытки (StudentAttempt: score, timing)
                → Ответы (Answer: is_correct, grading_status, ai_score)

Scores are StudentAttempt.score (set by the existing grading on finish);
pass/fail uses the test's own Test.passing_score. Counts and averages are
done in the database (annotate / aggregate / Subquery) with a fixed number
of queries per page, whatever the number of students, attempts or answers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from statistics import mean

from django.db.models import (
    Avg,
    Count,
    F,
    IntegerField,
    Max,
    Min,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
)
from django.db.models.functions import Coalesce

from apps.users.models import User

from ..models import (
    REVIEW_GRADING_STATUSES,
    Answer,
    AttemptStatus,
    GradingStatus,
    Question,
    SessionParticipant,
    StudentAttempt,
    TestSession,
)

# Result filter buckets (spec): label → (min, max) inclusive percent.
SCORE_BUCKETS = (
    ("90-100", "90–100%", 90, 100),
    ("80-89", "80–89%", 80, 89.999),
    ("70-79", "70–79%", 70, 79.999),
    ("60-69", "60–69%", 60, 69.999),
    ("lt60", "Ниже 60%", 0, 59.999),
)

# Distribution chart columns, low → high.
DISTRIBUTION_BUCKETS = (
    ("<50", 0, 49.999),
    ("50–59", 50, 59.999),
    ("60–69", 60, 69.999),
    ("70–79", 70, 79.999),
    ("80–89", 80, 89.999),
    ("90–100", 90, 100),
)

SUCCESS_BLOCK_SIZE = 5


# ---------------------------------------------------------------------------
# Scoping
# ---------------------------------------------------------------------------

def visible_sessions(user) -> QuerySet:
    """Sessions whose analytics ``user`` may see. Admins: all. Teachers (if
    ever given admin access): only their own sessions — the same rule as the
    teacher portal (TestSession.objects.for_teacher)."""
    sessions = TestSession.objects.all()
    if user.is_superuser or getattr(user, "role", None) == User.Role.ADMIN:
        return sessions
    teacher = getattr(user, "teacher_profile", None)
    if teacher is None:
        return sessions.none()
    return sessions.for_teacher(teacher)


def with_list_stats(sessions: QuerySet) -> QuerySet:
    """Session list columns (students, attempts, average) as subqueries —
    one query for the whole page, no row multiplication from joins."""
    # Students only: an LMS account's own attempt (StudentAttempt.user, e.g.
    # the Team Lead checking the test) never enters student statistics.
    finished = StudentAttempt.objects.filter(session=OuterRef("pk"), user__isnull=True, status=AttemptStatus.FINISHED)
    attempts = StudentAttempt.objects.filter(session=OuterRef("pk"), user__isnull=True)
    participants = SessionParticipant.objects.filter(session=OuterRef("pk"))

    def count(qs, expr="pk", distinct=False):
        return Subquery(
            qs.order_by().values("session").annotate(n=Count(expr, distinct=distinct)).values("n"),
            output_field=IntegerField(),
        )

    return sessions.select_related("group", "test", "test__subject", "teacher__user").annotate(
        roster_total=Coalesce(count(participants), 0),
        attempt_students=Coalesce(count(attempts, "student_name", distinct=True), 0),
        attempts_total=Coalesce(count(attempts), 0),
        finished_total=Coalesce(count(finished), 0),
        passed_total=Coalesce(count(finished.filter(score__gte=F("session__test__passing_score"))), 0),
        average_score=Subquery(finished.order_by().values("session").annotate(a=Avg("score")).values("a")[:1]),
    )


# ---------------------------------------------------------------------------
# One session
# ---------------------------------------------------------------------------

@dataclass
class StudentRow:
    key: str
    student_name: str
    student_id: int | None
    attempt: StudentAttempt | None
    attempts_count: int
    status: str            # finished / in_progress / expired / not_started
    status_label: str
    percent: float | None
    correct: int | None
    wrong: int | None
    pending: int | None
    total: int | None
    duration_seconds: int | None
    started_at: datetime | None
    finished_at: datetime | None
    passed: bool | None    # None: not finished, or answers still under review
    bucket: str | None = None
    number: int = 0


STATUS_LABELS = {
    "finished": "Завершён",
    "in_progress": "Проходит",
    "expired": "Время истекло",
    "not_started": "Не начал",
}


def _attempts_with_counts(attempts: QuerySet) -> QuerySet:
    return attempts.select_related("student").annotate(
        correct_count=Count("answers", filter=Q(answers__is_correct=True)),
        wrong_count=Count("answers", filter=Q(answers__is_correct=False)),
        pending_count=Count("answers", filter=Q(answers__grading_status__in=REVIEW_GRADING_STATUSES)),
        answered_count=Count("answers"),
    )


def _bucket(percent: float | None) -> str | None:
    if percent is None:
        return None
    for key, _label, low, high in SCORE_BUCKETS:
        if low <= percent <= high:
            return key
    return None


def student_rows(session: TestSession) -> list[StudentRow]:
    """One row per student: their latest attempt (earlier ones are counted
    in ``attempts_count``), plus roster students who never started."""
    passing = session.test.passing_score
    attempts = list(_attempts_with_counts(session.attempts.filter(user__isnull=True).order_by("started_at")))
    latest: dict[str, StudentAttempt] = {}
    counts: dict[str, int] = {}
    for attempt in attempts:
        key = f"s{attempt.student_id}" if attempt.student_id else f"n{attempt.student_name}"
        latest[key] = attempt
        counts[key] = counts.get(key, 0) + 1

    rows: list[StudentRow] = []
    for key, attempt in latest.items():
        finished = attempt.status == AttemptStatus.FINISHED
        total = len(attempt.question_ids) or attempt.answered_count or None
        percent = attempt.score if finished else None
        status = {
            AttemptStatus.FINISHED: "finished",
            AttemptStatus.ACTIVE: "in_progress",
            AttemptStatus.EXPIRED: "expired",
        }[attempt.status]
        wrong = None
        if finished and total is not None:
            # Unanswered questions count as wrong; answers under review don't.
            wrong = max(total - attempt.correct_count - attempt.pending_count, 0)
        rows.append(StudentRow(
            key=key,
            student_name=str(attempt.student) if attempt.student_id else attempt.student_name,
            student_id=attempt.student_id,
            attempt=attempt,
            attempts_count=counts[key],
            status=status,
            status_label=STATUS_LABELS[status],
            percent=percent,
            correct=attempt.correct_count if finished else None,
            wrong=wrong,
            pending=attempt.pending_count if finished else None,
            total=total,
            duration_seconds=int(attempt.duration_seconds) if attempt.duration_seconds is not None else None,
            started_at=attempt.started_at,
            finished_at=attempt.finished_at,
            passed=(None if not finished or attempt.pending_count else percent >= passing),
            bucket=_bucket(percent),
        ))

    seen_students = {row.student_id for row in rows if row.student_id}
    for participant in session.participants.select_related("student"):
        if participant.student_id not in seen_students:
            rows.append(StudentRow(
                key=f"s{participant.student_id}", student_name=str(participant.student),
                student_id=participant.student_id, attempt=None, attempts_count=0,
                status="not_started", status_label=STATUS_LABELS["not_started"], percent=None,
                correct=None, wrong=None, pending=None, total=None, duration_seconds=None,
                started_at=None, finished_at=None, passed=None,
            ))
    rows.sort(key=lambda r: (r.percent is None, -(r.percent or 0), r.student_name.casefold()))
    for number, row in enumerate(rows, start=1):
        row.number = number
    return rows


RESULT_FILTERS = (
    ("passed", "Прошли"),
    ("failed", "Не прошли"),
    ("review", "На проверке"),
    *((key, label) for key, label, _low, _high in SCORE_BUCKETS),
)

STATUS_FILTERS = tuple(STATUS_LABELS.items())


def filter_rows(rows: list[StudentRow], *, status: str = "", result: str = "", query: str = "") -> list[StudentRow]:
    """Students table filters: status, result (pass/fail/review or a score
    bucket) and a name search."""
    query = query.strip().casefold()

    def result_ok(row: StudentRow) -> bool:
        if not result:
            return True
        if result == "passed":
            return row.passed is True
        if result == "failed":
            return row.passed is False
        if result == "review":
            return row.status == "finished" and row.passed is None
        return row.bucket == result

    return [
        r for r in rows
        if (not status or r.status == status)
        and result_ok(r)
        and (not query or query in r.student_name.casefold())
    ]


@dataclass
class QuestionStat:
    number: int
    question: Question
    answered: int
    correct: int
    wrong: int
    pending: int
    ai_scored: int
    ai_score_avg: float | None

    @property
    def rate(self) -> int | None:
        graded = self.correct + self.wrong
        return round(self.correct / graded * 100) if graded else None


def question_stats(sessions: QuerySet | list, questions: QuerySet) -> list[QuestionStat]:
    """Per-question answer statistics over the given sessions — one query."""
    by_question = {
        row["question_id"]: row
        for row in Answer.objects.filter(attempt__session__in=sessions)
        .values("question_id")
        .annotate(
            answered=Count("pk"),
            correct=Count("pk", filter=Q(is_correct=True)),
            wrong=Count("pk", filter=Q(is_correct=False)),
            pending=Count("pk", filter=Q(grading_status__in=REVIEW_GRADING_STATUSES)),
            ai_scored=Count("ai_score"),
            ai_score_avg=Avg("ai_score"),
        )
    }
    stats = []
    for number, question in enumerate(questions, start=1):
        row = by_question.get(question.pk, {})
        stats.append(QuestionStat(
            number=number,
            question=question,
            answered=row.get("answered", 0),
            correct=row.get("correct", 0),
            wrong=row.get("wrong", 0),
            pending=row.get("pending", 0),
            ai_scored=row.get("ai_scored", 0),
            ai_score_avg=row.get("ai_score_avg"),
        ))
    return stats


def success_extremes(stats: list[QuestionStat]) -> tuple[list[QuestionStat], list[QuestionStat]]:
    """(lowest success, highest success) — graded questions only, no overlap."""
    graded = [s for s in stats if s.rate is not None]
    low = sorted(graded, key=lambda s: (s.rate, -s.answered))[:SUCCESS_BLOCK_SIZE]
    low_ids = {s.question.pk for s in low if s.rate < 100}
    low = [s for s in low if s.question.pk in low_ids]
    high = [s for s in sorted(graded, key=lambda s: (-s.rate, -s.answered)) if s.question.pk not in low_ids]
    return low, high[:SUCCESS_BLOCK_SIZE]


@dataclass
class GradingCounts:
    """Answer.grading_status, grouped the way the LMS describes them."""

    auto: int = 0          # AUTO — choice questions and text with accepted answers
    pending: int = 0       # PENDING + PROCESSING
    ai_done: int = 0       # AI (legacy) + DONE
    manual: int = 0        # MANUAL
    ai_failed: int = 0     # FAILED
    ai_confidence_avg: float | None = None


def grading_counts(answers: QuerySet) -> GradingCounts:
    counts = GradingCounts()
    for row in answers.values("grading_status").annotate(n=Count("pk")).order_by():
        status, n = row["grading_status"], row["n"]
        if status == GradingStatus.AUTO:
            counts.auto += n
        elif status in (GradingStatus.PENDING, GradingStatus.PROCESSING):
            counts.pending += n
        elif status in (GradingStatus.AI, GradingStatus.DONE):
            counts.ai_done += n
        elif status == GradingStatus.MANUAL:
            counts.manual += n
        elif status == GradingStatus.FAILED:
            counts.ai_failed += n
    counts.ai_confidence_avg = answers.aggregate(c=Avg("ai_confidence"))["c"]
    return counts


@dataclass
class Summary:
    """Aggregated results of finished attempts (a session, test, subject…)."""

    attempts: int = 0
    students: int = 0
    average: float | None = None
    best: float | None = None
    worst: float | None = None
    passed: int = 0
    average_seconds: int | None = None

    @property
    def pass_rate(self) -> float | None:
        return round(self.passed / self.attempts * 100, 1) if self.attempts else None


def summarize_attempts(attempts: QuerySet) -> Summary:
    """Finished attempts → one aggregate query + one light values_list for
    durations (portable across PostgreSQL/SQLite). Pass uses each attempt's
    own test passing score."""
    finished = attempts.filter(status=AttemptStatus.FINISHED)
    agg = finished.aggregate(
        n=Count("pk"),
        students=Count("student_name", distinct=True),
        avg=Avg("score"),
        best=Max("score"),
        worst=Min("score"),
        passed=Count("pk", filter=Q(score__gte=F("session__test__passing_score"))),
    )
    durations = [
        (end - start).total_seconds()
        for start, end in finished.values_list("started_at", "finished_at")
        if start and end
    ]
    return Summary(
        attempts=agg["n"],
        students=agg["students"],
        average=round(agg["avg"], 1) if agg["avg"] is not None else None,
        best=agg["best"],
        worst=agg["worst"],
        passed=agg["passed"],
        average_seconds=int(mean(durations)) if durations else None,
    )


@dataclass
class SessionAnalytics:
    rows: list[StudentRow]
    total_students: int
    finished: int
    passed: int
    failed: int
    under_review: int
    not_finished: int
    average: float | None
    best: float | None
    worst: float | None
    average_seconds: int | None
    distribution: list[dict] = field(default_factory=list)
    questions: list[QuestionStat] = field(default_factory=list)
    low_success: list[QuestionStat] = field(default_factory=list)
    high_success: list[QuestionStat] = field(default_factory=list)
    grading: GradingCounts | None = None

    def share(self, n: int) -> float:
        return round(n / self.total_students * 100, 1) if self.total_students else 0.0

    @property
    def pass_rate(self) -> float | None:
        return self.share(self.passed) if self.total_students else None


def session_analytics(session: TestSession) -> SessionAnalytics:
    rows = student_rows(session)
    finished_rows = [r for r in rows if r.status == "finished"]
    scores = [r.percent for r in finished_rows if r.percent is not None]
    durations = [r.duration_seconds for r in finished_rows if r.duration_seconds is not None]

    distribution = []
    peak = 0
    for label, low, high in DISTRIBUTION_BUCKETS:
        n = sum(1 for s in scores if low <= s <= high)
        peak = max(peak, n)
        distribution.append({"label": label, "count": n})
    for column in distribution:
        column["height"] = round(column["count"] / peak * 100) if peak else 0

    questions = question_stats(
        [session.pk], session.test.questions.order_by("order", "created_at"),
    )
    low, high = success_extremes(questions)
    passed = sum(1 for r in rows if r.passed is True)
    failed = sum(1 for r in rows if r.passed is False)
    under_review = sum(1 for r in finished_rows if r.passed is None)
    return SessionAnalytics(
        rows=rows,
        total_students=len(rows),
        finished=len(finished_rows),
        passed=passed,
        failed=failed,
        under_review=under_review,
        not_finished=len(rows) - len(finished_rows),
        average=round(mean(scores), 1) if scores else None,
        best=max(scores) if scores else None,
        worst=min(scores) if scores else None,
        average_seconds=int(mean(durations)) if durations else None,
        distribution=distribution,
        questions=questions,
        low_success=low,
        high_success=high,
        grading=grading_counts(Answer.objects.filter(attempt__session=session)),
    )


# ---------------------------------------------------------------------------
# Attempt detail
# ---------------------------------------------------------------------------

def attempt_detail(attempt: StudentAttempt) -> dict:
    """Question by question: the student's answer, the correct one, the result
    (incl. grading status and AI score for text/code)."""
    from .attempts import ordered_questions, result_rows

    rows = result_rows(attempt) if attempt.question_ids else []
    if not attempt.question_ids:
        # Legacy attempt: just the questions it has answers for.
        answered = list(attempt.answers.values_list("question_id", flat=True))
        questions = ordered_questions(attempt.session.test, [str(q) for q in answered])
        answers = {a.question_id: a for a in attempt.answers.all()}
        for number, question in enumerate(questions, start=1):
            answer = answers.get(question.pk)
            options = {str(o.pk): o for o in question.display_options}
            rows.append({
                "number": number,
                "question": question,
                "answer": answer,
                "selected": [options[i] for i in (answer.selected_options if answer else []) if i in options],
                "correct_options": [o for o in question.display_options if o.is_correct],
                "status": "pending" if answer and answer.is_correct is None else (
                    "correct" if answer and answer.is_correct else "wrong"
                ),
            })
    correct = sum(1 for r in rows if r["status"] == "correct")
    pending = sum(1 for r in rows if r["status"] == "pending")
    return {
        "rows": rows,
        "correct": correct,
        "pending": pending,
        "total": len(rows),
        "passed": (None if attempt.status != AttemptStatus.FINISHED or pending
                   else attempt.score >= attempt.session.test.passing_score),
    }


# ---------------------------------------------------------------------------
# Above one session: test, subject, group, the whole tree
# ---------------------------------------------------------------------------

@dataclass
class TestSummary:
    """Finished attempts of one test (within a group, if grouped by it)."""

    group_id: int | None
    subject_id: int | None
    test_id: object
    sessions: int
    attempts: int
    students: int
    average: float | None
    best: float | None
    worst: float | None
    passed: int

    @property
    def pass_rate(self) -> float | None:
        return round(self.passed / self.attempts * 100, 1) if self.attempts else None


def test_summaries(attempts: QuerySet, *, by_group: bool = True) -> dict[tuple, TestSummary]:
    """Finished attempts grouped by (group, subject, test) — one query.
    Key: (group_id, subject_id, test_id), group_id is None when not by_group."""
    keys = ["session__test__subject", "session__test"]
    if by_group:
        keys.insert(0, "session__group")
    rows = (
        attempts.filter(status=AttemptStatus.FINISHED)
        .order_by()
        .values(*keys)
        .annotate(
            sessions=Count("session", distinct=True),
            n=Count("pk"),
            students=Count("student_name", distinct=True),
            avg=Avg("score"),
            best=Max("score"),
            worst=Min("score"),
            passed=Count("pk", filter=Q(score__gte=F("session__test__passing_score"))),
        )
    )
    result = {}
    for row in rows:
        key = (row.get("session__group"), row["session__test__subject"], row["session__test"])
        result[key] = TestSummary(
            group_id=key[0], subject_id=key[1], test_id=key[2],
            sessions=row["sessions"], attempts=row["n"], students=row["students"],
            average=round(row["avg"], 1) if row["avg"] is not None else None,
            best=row["best"], worst=row["worst"], passed=row["passed"],
        )
    return result


def finished_attempts_of(sessions: QuerySet) -> QuerySet:
    return StudentAttempt.objects.filter(session__in=sessions, user__isnull=True)


@dataclass
class TreeNode:
    """One level of Группа → Предмет → Тест → Сессии."""

    key: object
    label: str
    obj: object = None
    summary: Summary | TestSummary | None = None
    children: list = field(default_factory=list)
    sessions: list = field(default_factory=list)


def _merge(summaries: list[TestSummary]) -> Summary:
    """Weighted roll-up of test summaries (no extra query)."""
    attempts = sum(s.attempts for s in summaries)
    if not attempts:
        return Summary()
    weighted = sum((s.average or 0) * s.attempts for s in summaries)
    bests = [s.best for s in summaries if s.best is not None]
    worsts = [s.worst for s in summaries if s.worst is not None]
    return Summary(
        attempts=attempts,
        students=sum(s.students for s in summaries),  # upper bound across tests
        average=round(weighted / attempts, 1),
        best=max(bests) if bests else None,
        worst=min(worsts) if worsts else None,
        passed=sum(s.passed for s in summaries),
    )


def analytics_tree(sessions: QuerySet) -> list[TreeNode]:
    """Группа → Предмет → Тест → Сессии, with roll-up results at every level.
    Two queries: the sessions (with list stats) and the per-test summaries."""
    session_list = list(with_list_stats(sessions).order_by("-created_at"))
    summaries = test_summaries(finished_attempts_of(sessions))

    groups: dict = {}
    for session in session_list:
        group_key = session.group_id
        subject = session.test.subject
        group = groups.setdefault(group_key, TreeNode(
            key=group_key, label=session.group.name if session.group_id else "Без группы", obj=session.group,
        ))
        subjects = {node.key: node for node in group.children}
        subject_node = subjects.get(subject.pk if subject else None)
        if subject_node is None:
            subject_node = TreeNode(key=subject.pk if subject else None,
                                    label=subject.name if subject else "Без предмета", obj=subject)
            group.children.append(subject_node)
        tests = {node.key: node for node in subject_node.children}
        test_node = tests.get(session.test_id)
        if test_node is None:
            test_node = TreeNode(
                key=session.test_id, label=session.test.title, obj=session.test,
                summary=summaries.get((group_key, subject_node.key, session.test_id)),
            )
            subject_node.children.append(test_node)
        test_node.sessions.append(session)

    tree = sorted(groups.values(), key=lambda n: (n.key is None, n.label.casefold()))
    for group in tree:
        group.children.sort(key=lambda n: (n.key is None, n.label.casefold()))
        for subject_node in group.children:
            subject_node.children.sort(key=lambda n: n.label.casefold())
            subject_node.summary = _merge([t.summary for t in subject_node.children if t.summary])
        group.summary = _merge([t.summary for s in group.children for t in s.children if t.summary])
    return tree


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

EXPORT_HEADERS = [
    "Группа", "Предмет", "Тест", "Сессия", "Студент", "Результат",
    "Правильных", "Неправильных", "Время", "Статус",
]


def export_rows(session: TestSession, rows: list[StudentRow]) -> list[list[str]]:
    from .sessions import display_title, format_duration

    group = session.group.name if session.group_id else "—"
    subject = session.test.subject.name if session.test.subject_id else "—"
    result = []
    for row in rows:
        status = row.status_label
        if row.passed is True:
            status += " · прошёл"
        elif row.passed is False:
            status += " · не прошёл"
        elif row.status == "finished":
            status += " · на проверке"
        result.append([
            group,
            subject,
            session.test.title,
            display_title(session),
            row.student_name,
            "—" if row.percent is None else f"{row.percent:g}%",
            "—" if row.correct is None else str(row.correct),
            "—" if row.wrong is None else str(row.wrong),
            format_duration(row.duration_seconds),
            status,
        ])
    return result


def export_csv(session: TestSession, rows: list[StudentRow]) -> bytes:
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(EXPORT_HEADERS)
    writer.writerows(export_rows(session, rows))
    # BOM: Excel opens UTF-8 CSV with Cyrillic correctly.
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


def export_excel(session: TestSession, rows: list[StudentRow], analytics: SessionAnalytics) -> bytes:
    import io

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    from .sessions import subtitle, display_title

    wb = Workbook()
    ws = wb.active
    ws.title = "Результаты"
    ws["A1"] = f"Результаты сессии: {display_title(session)}"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = subtitle(session)
    ws["A2"].font = Font(color="68736C")
    ws["A3"] = _kpi_line(session, analytics)
    header_row = 5
    fill = PatternFill("solid", fgColor="E7F3EC")
    for col, title in enumerate(EXPORT_HEADERS, start=1):
        cell = ws.cell(row=header_row, column=col, value=title)
        cell.font = Font(bold=True, color="1F5F3C")
        cell.fill = fill
        cell.alignment = Alignment(vertical="center")
    for r, row in enumerate(export_rows(session, rows), start=header_row + 1):
        for c, value in enumerate(row, start=1):
            ws.cell(row=r, column=c, value=value)
    for col, width in enumerate([18, 16, 28, 28, 30, 11, 12, 14, 10, 26], start=1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)

    qs = wb.create_sheet("Вопросы")
    headers = ["№", "Вопрос", "Тип", "Сложность", "Ответили", "Правильно", "Неправильно", "% правильных"]
    for col, title in enumerate(headers, start=1):
        cell = qs.cell(row=1, column=col, value=title)
        cell.font = Font(bold=True, color="1F5F3C")
        cell.fill = fill
    for r, stat in enumerate(analytics.questions, start=2):
        q = stat.question
        values = [stat.number, q.text, q.get_question_type_display(), q.get_difficulty_display(),
                  stat.answered, stat.correct, stat.wrong, "—" if stat.rate is None else f"{stat.rate}%"]
        for c, value in enumerate(values, start=1):
            qs.cell(row=r, column=c, value=value)
    for col, width in enumerate([5, 60, 16, 12, 10, 10, 12, 13], start=1):
        qs.column_dimensions[get_column_letter(col)].width = width

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _kpi_line(session: TestSession, a: SessionAnalytics) -> str:
    def pct(v):
        return "—" if v is None else f"{v:g}%"

    return (
        f"Студентов: {a.total_students} · Прошли: {a.passed} · Не прошли: {a.failed} · "
        f"Средний: {pct(a.average)} · Макс.: {pct(a.best)} · Мин.: {pct(a.worst)} · "
        f"Проходной балл: {session.test.passing_score}%"
    )


def export_pdf(session: TestSession, rows: list[StudentRow], analytics: SessionAnalytics) -> bytes:
    """Same reportlab mechanism (and fonts) as the academy monthly report."""
    import io
    from xml.sax.saxutils import escape

    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from apps.academy.services.monthly_report_pdf import (
        _BOLD, _REGULAR, BORDER, BRAND_DARK, BRAND_SOFT, INK, INK_SECONDARY, _ensure_fonts,
    )

    from .sessions import subtitle, display_title

    _ensure_fonts()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=28, rightMargin=28, topMargin=32, bottomMargin=32,
                            title=f"Результаты: {display_title(session)}")
    title_style = ParagraphStyle("t", fontName=_BOLD, fontSize=16, leading=20, textColor=INK)
    sub_style = ParagraphStyle("s", fontName=_REGULAR, fontSize=9.5, leading=13, textColor=INK_SECONDARY)
    cell_style = ParagraphStyle("c", fontName=_REGULAR, fontSize=8, leading=10, textColor=INK)
    head_style = ParagraphStyle("h", fontName=_BOLD, fontSize=8, leading=10, textColor=BRAND_DARK)
    data = [[Paragraph(escape(h), head_style) for h in EXPORT_HEADERS]]
    data += [[Paragraph(escape(v), cell_style) for v in row] for row in export_rows(session, rows)]
    table = Table(data, repeatRows=1, colWidths=[72, 64, 96, 96, 120, 52, 52, 60, 44, 90])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_SOFT),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story = [
        Paragraph(escape(f"Результаты сессии: {display_title(session)}"), title_style),
        Spacer(1, 4),
        Paragraph(escape(subtitle(session)), sub_style),
        Paragraph(escape(_kpi_line(session, analytics)), sub_style),
        Spacer(1, 12),
        table if rows else Paragraph("Результатов пока нет.", sub_style),
    ]
    doc.build(story)
    return buffer.getvalue()
