"""Forms of the «Тесты» admin section (apps/testing/admin_views.py)."""
from __future__ import annotations

from datetime import datetime, timedelta

from django import forms
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.academy.models import Group, Student

from .models import (
    MAX_SESSION_DURATION,
    AnswerMatch,
    DifficultyLevel,
    ProgrammingLanguage,
    Question,
    QuestionType,
    SessionStatus,
    SessionType,
    Test,
    TestSession,
    TestStatus,
)
from .services.participants import set_roster
from .services.question_rules import CodeTestData, OptionData, QuestionData


class StyledFormMixin:
    """``ok-input`` on every non-checkbox widget (checkboxes are wrapped in
    a ``label.ok-check`` by the templates)."""

    def _style(self):
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "ok-input")


class DateTimeLocalInput(forms.DateTimeInput):
    input_type = "datetime-local"

    def __init__(self, attrs=None):
        super().__init__(attrs, format="%Y-%m-%dT%H:%M")


INFO_FIELDS = ("title", "description", "image_url", "subject", "level")
SETTINGS_FIELDS = (
    "status", "time_limit_minutes", "max_attempts", "passing_score", "questions_per_attempt",
    "shuffle_questions", "shuffle_options", "show_result", "show_correct_answers", "allow_retry",
    "available_from", "available_until",
)


class TestInfoForm(StyledFormMixin, forms.ModelForm):
    """«Основная информация» on the test page."""

    class Meta:
        model = Test
        fields = INFO_FIELDS
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["subject"].empty_label = "— Без предмета —"
        self.fields["subject"].help_text = ""
        self._style()


class TestCreateForm(StyledFormMixin, forms.ModelForm):
    """«Создать тест»: main info plus the settings a test usually needs first."""

    class Meta:
        model = Test
        fields = (*INFO_FIELDS, "status", "time_limit_minutes", "max_attempts", "passing_score")
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["subject"].empty_label = "— Без предмета —"
        self.fields["subject"].help_text = ""
        self._style()


class TestSettingsForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Test
        fields = SETTINGS_FIELDS
        widgets = {"available_from": DateTimeLocalInput(), "available_until": DateTimeLocalInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("available_from", "available_until"):
            self.fields[name].input_formats = ["%Y-%m-%dT%H:%M"]
        self._style()


class SessionForm(StyledFormMixin, forms.Form):
    """«Создание сессии» and the session's «Настройки».

    A session is held for a group — all of its active students or chosen
    ones (the roster, SessionParticipant). The date with start/end time is
    optional together: without it the session is a «Черновик» started by
    hand; with it, «Запланирована» and it opens/closes by itself.
    """

    title = forms.CharField(label="Название сессии", max_length=255, required=False)
    test = forms.ModelChoiceField(label="Тест", queryset=Test.objects.none(), empty_label="— Выберите тест —")
    group = forms.ModelChoiceField(label="Группа", queryset=Group.objects.none(), empty_label="— Выберите группу —")
    all_students = forms.BooleanField(label="Все студенты группы", required=False, initial=True)
    students = forms.MultipleChoiceField(label="Студенты", required=False)
    date = forms.DateField(label="Дата", required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    start_time = forms.TimeField(label="Время начала", required=False, widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"))
    end_time = forms.TimeField(label="Время окончания", required=False, widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"))
    max_attempts = forms.IntegerField(
        label="Количество попыток", min_value=1, max_value=20, required=False, initial=1,
        help_text="Пусто — без ограничений.",
    )
    # Settings tab only (the create page keeps the spec's short form).
    session_type = forms.ChoiceField(label="Режим", choices=SessionType.choices, initial=SessionType.EXAM)
    time_limit_minutes = forms.IntegerField(
        label="Время на прохождение, мин", min_value=1, max_value=720, required=False,
        help_text="Переопределяет время из настроек теста. Пусто — как в тесте.",
    )

    def __init__(self, *args, session: TestSession | None = None, **kwargs):
        self.session = session
        if session is not None and not args and "initial" not in kwargs:
            kwargs["initial"] = self.initial_for(session)
        super().__init__(*args, **kwargs)
        tests = Test.objects.filter(status=TestStatus.ACTIVE)
        if session is not None:
            tests = Test.objects.filter(Q(status=TestStatus.ACTIVE) | Q(pk=session.test_id))
        self.fields["test"].queryset = tests.select_related("subject").order_by("title")
        self.fields["group"].queryset = Group.objects.order_by("name")
        group_id = self.data.get("group") if self.is_bound else (self.initial.get("group") or None)
        self.fields["students"].choices = [(str(s.pk), str(s)) for s in self.group_students(group_id)]
        if session is not None and session.participants.exclude(status="not_started").exists():
            # Started students can't be moved to another group's session.
            self.fields["group"].disabled = True
        self._style()

    @staticmethod
    def group_students(group_id):
        if not group_id or not str(group_id).isdigit():
            return Student.objects.none()
        return Student.objects.filter(group_id=group_id, status=Student.Status.ACTIVE).order_by("first_name", "last_name")

    @staticmethod
    def initial_for(session: TestSession) -> dict:
        start = timezone.localtime(session.scheduled_start) if session.scheduled_start else None
        end = timezone.localtime(session.scheduled_end) if session.scheduled_end else None
        roster = [str(pk) for pk in session.participants.values_list("student_id", flat=True)]
        group_size = SessionForm.group_students(session.group_id).count() if session.group_id else 0
        return {
            "title": session.title,
            "test": session.test_id,
            "group": session.group_id,
            "all_students": not roster or len(roster) >= group_size,
            "students": roster,
            "date": start.date() if start else None,
            "start_time": start.time() if start else None,
            "end_time": end.time() if end else None,
            "max_attempts": session.max_attempts_per_student,
            "session_type": session.session_type,
            "time_limit_minutes": session.time_limit_minutes,
        }

    def clean(self):
        data = super().clean()
        date, start, end = data.get("date"), data.get("start_time"), data.get("end_time")
        if any(v is not None for v in (date, start, end)):
            if date is None:
                self.add_error("date", "Укажите дату.")
            if start is None:
                self.add_error("start_time", "Укажите время начала.")
            if end is None:
                self.add_error("end_time", "Укажите время окончания.")
            if date and start and end:
                if end <= start:
                    self.add_error("end_time", "Время окончания должно быть позже начала.")
                elif datetime.combine(date, end) - datetime.combine(date, start) > MAX_SESSION_DURATION:
                    self.add_error("end_time", "Сессия не может длиться больше 12 часов.")
                else:
                    data["scheduled_start"] = timezone.make_aware(datetime.combine(date, start))
                    data["scheduled_end"] = timezone.make_aware(datetime.combine(date, end))
        group = data.get("group") or (self.session.group if self.session else None)
        if group is not None:
            students = list(self.group_students(group.pk))
            if data.get("all_students"):
                data["roster"] = students
            else:
                chosen = set(data.get("students") or [])
                data["roster"] = [s for s in students if str(s.pk) in chosen]
                if not data["roster"]:
                    self.add_error("students", "Выберите хотя бы одного студента или отметьте «Все студенты».")
        return data

    def save(self, teacher=None) -> TestSession:
        data = self.cleaned_data
        session = self.session or TestSession(teacher=teacher)
        session.title = data["title"].strip()
        session.test = data["test"]
        session.group = data.get("group") or session.group
        session.session_type = data.get("session_type") or session.session_type or SessionType.EXAM
        session.time_limit_minutes = data.get("time_limit_minutes")
        session.max_attempts_per_student = data.get("max_attempts")
        old_end = session.scheduled_end
        session.scheduled_start = data.get("scheduled_start")
        session.scheduled_end = data.get("scheduled_end")
        if session.is_training:
            session.duration = None
        elif session.status == SessionStatus.CREATED and not session.scheduled_start and session.duration is None:
            # A draft exam without a schedule: its window = the test's time (or 1 h).
            session.duration = timedelta(minutes=session.effective_time_limit_minutes or 60)
        if (
            session.pk and session.is_exam and session.status in (SessionStatus.RUNNING, SessionStatus.PAUSED)
            and session.scheduled_end and session.scheduled_end != old_end
        ):
            session.expires_at = session.scheduled_end  # moving the end of a running exam
        session.full_clean(exclude=["key"])
        with transaction.atomic():
            session.save()
            set_roster(session, data["roster"])
        session.sync_schedule()
        return session


class QuestionForm(StyledFormMixin, forms.Form):
    """Fields of the question editor that are plain values. Options, accepted
    answers and code tests come as repeated POST rows (see from_post)."""

    question_type = forms.ChoiceField(label="Тип вопроса", choices=QuestionType.choices)
    text = forms.CharField(label="Текст вопроса", widget=forms.Textarea(attrs={"rows": 3}), required=False)
    # Checked (http/https only) together with the option images in
    # services/question_rules.py, so editor and API reject the same URLs.
    image_url = forms.CharField(label="Изображение вопроса", required=False, max_length=1000)
    hint = forms.CharField(label="Подсказка", widget=forms.Textarea(attrs={"rows": 2}), required=False)
    points = forms.IntegerField(label="Баллы", min_value=1, max_value=100, initial=1)
    is_required = forms.BooleanField(label="Обязательный вопрос", required=False, initial=True)
    difficulty = forms.ChoiceField(label="Сложность", choices=DifficultyLevel.choices, initial=DifficultyLevel.MEDIUM)
    language = forms.ChoiceField(
        label="Язык программирования", required=False,
        choices=[("", "— Выберите язык —"), *[c for c in ProgrammingLanguage.choices if c[0]]],
    )
    answer_match = forms.ChoiceField(label="Проверка ответа", choices=AnswerMatch.choices, initial=AnswerMatch.IGNORE_CASE)
    starter_code = forms.CharField(label="Стартовый код", widget=forms.Textarea(attrs={"rows": 8}), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()

    @classmethod
    def initial_for(cls, question: Question) -> dict:
        return {name: getattr(question, name) for name in cls.base_fields}

    def extra_values(self) -> dict:
        data = self.cleaned_data
        return {name: data[name] for name in ("hint", "points", "is_required", "answer_match", "starter_code", "difficulty")}


def question_data_from_post(post, question_type: str, text: str, language: str, image_url: str = "") -> QuestionData:
    """Repeated editor rows → QuestionData.

    option_text / option_id / option_image are parallel lists; correctness comes from
    ``option_correct`` (checkbox values = row index) or ``option_correct_single``
    (radio value = row index). Accepted answers: ``correct_answer`` (main) +
    ``accepted_answers`` (one per line). Code tests: test_input / test_output.
    """
    texts = post.getlist("option_text")
    ids = post.getlist("option_id")
    images = post.getlist("option_image")
    if question_type == QuestionType.SINGLE_CHOICE:
        correct = {post.get("option_correct_single", "")}
    else:
        correct = set(post.getlist("option_correct"))
    options = [
        OptionData(
            text=t,
            is_correct=str(i) in correct,
            id=(ids[i] if i < len(ids) and ids[i] else None),
            image_url=images[i] if i < len(images) else "",
        )
        for i, t in enumerate(texts)
    ]
    accepted = [post.get("correct_answer", ""), *post.get("accepted_answers", "").splitlines()]
    inputs, outputs = post.getlist("test_input"), post.getlist("test_output")
    tests = [CodeTestData(i, o) for i, o in zip(inputs, outputs)]
    # The editor posts every section; only the chosen type's rows count
    # (switching a filled single-choice question to «Текст» drops its options).
    if question_type not in (QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE):
        options = []
    if question_type != QuestionType.TEXT:
        accepted = []
    if question_type != QuestionType.CODE:
        tests = []
    return QuestionData(
        question_type=question_type, text=text, language=language, image_url=image_url,
        correct_answers=accepted, options=options, code_tests=tests,
    )
