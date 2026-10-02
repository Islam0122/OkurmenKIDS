"""Forms of the «Тесты» admin section (apps/testing/admin_views.py)."""
from __future__ import annotations

from datetime import timedelta

from django import forms

from apps.academy.models import Group

from .models import (
    AnswerMatch,
    DifficultyLevel,
    ProgrammingLanguage,
    Question,
    QuestionType,
    SessionType,
    Test,
    TestSession,
)
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


class SessionCreateForm(StyledFormMixin, forms.Form):
    """Launch a test for students: a TestSession with its own key."""

    session_type = forms.ChoiceField(label="Режим", choices=SessionType.choices, initial=SessionType.EXAM)
    group = forms.ModelChoiceField(
        label="Группа", queryset=Group.objects.order_by("name"), required=False, empty_label="— Любые студенты —",
        help_text="Если указана, студенты выбирают себя из списка группы.",
    )
    title = forms.CharField(label="Название сессии", max_length=255, required=False)
    duration_minutes = forms.IntegerField(
        label="Длительность сессии, мин", min_value=1, max_value=720, required=False,
        help_text="Для экзамена: сколько сессия принимает ответы после запуска.",
    )
    start_now = forms.BooleanField(label="Сразу запустить", required=False, initial=True)

    def __init__(self, *args, test: Test, **kwargs):
        super().__init__(*args, **kwargs)
        self.test = test
        self.fields["duration_minutes"].initial = test.time_limit_minutes or 60
        self._style()

    def clean(self):
        data = super().clean()
        if data.get("session_type") == SessionType.EXAM and not data.get("duration_minutes"):
            self.add_error("duration_minutes", "Укажите длительность экзамена.")
        return data

    def save(self, teacher=None) -> TestSession:
        data = self.cleaned_data
        is_exam = data["session_type"] == SessionType.EXAM
        session = TestSession(
            test=self.test,
            group=data["group"],
            teacher=teacher,
            session_type=data["session_type"],
            title=data["title"].strip(),
            duration=timedelta(minutes=data["duration_minutes"]) if is_exam else None,
            max_attempts_per_student=self.test.effective_max_attempts,
        )
        session.full_clean()
        session.save()
        if data["start_now"]:
            session.start()
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
