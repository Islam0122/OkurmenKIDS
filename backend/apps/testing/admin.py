"""Django admin for the test bank: Test → Question → QuestionOption.

Only the authoring side lives here (tests, their questions and answer
options). Sessions, attempts and grading are out of scope for this admin.

* TestAdmin — the «Тесты» list (level/status filters, question count) and
  a change page that lists the test's questions with drag & drop ordering
  (admin/testing/test/change_form.html + static/testing/admin/*).
* QuestionAdmin — the full question list with filters, plus the question
  form with an inline of answer options that is only shown for
  single/multiple choice questions.
"""
from __future__ import annotations

import json

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.utils import unquote
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Max
from django.http import HttpResponseNotAllowed, HttpResponseRedirect, JsonResponse
from django.urls import path, reverse
from django.utils import formats, timezone

from .models import DifficultyLevel, Question, QuestionOption, QuestionType, Test
from .templatetags.question_bank import active_badge, difficulty_badge, plural_ru, question_count_label

CHOICE_TYPES = (QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE)

# Query flag on question add/change links coming from a test's page: after
# «Сохранить» the admin goes back to that test instead of the question list.
FROM_TEST_PARAM = "_from"
FROM_TEST_VALUE = "test"

ADMIN_CSS = {"all": ("testing/admin/testing_admin.css",)}


def _created_display(value) -> str:
    """`6 июня 2026 11:32` (local time, genitive month)."""
    return formats.date_format(timezone.localtime(value), "j E Y H:i") if value else "—"


# ---------------------------------------------------------------------------
# List filters
# ---------------------------------------------------------------------------

class DropdownFilterMixin:
    """Jazzmin dropdown with a visible label and an explicit «Все» option."""

    template = "admin/testing/dropdown_filter.html"


class LevelListFilter(DropdownFilterMixin, admin.ChoicesFieldListFilter):
    pass


class TestStatusFilter(DropdownFilterMixin, admin.SimpleListFilter):
    title = "Статус"
    parameter_name = "status"

    def lookups(self, request, model_admin):
        return (("active", "Активен"), ("inactive", "Неактивен"))

    def queryset(self, request, queryset):
        if self.value() == "active":
            return queryset.filter(is_active=True)
        if self.value() == "inactive":
            return queryset.filter(is_active=False)
        return queryset


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

@admin.register(Test)
class TestAdmin(admin.ModelAdmin):
    list_display = ("title", "level_badge", "status_badge", "question_count_display", "created_display")
    list_display_links = ("title",)
    list_filter = (("level", LevelListFilter), TestStatusFilter)
    search_fields = ("title", "description")
    search_help_text = "Название или описание"
    list_per_page = 25
    actions = ("activate_tests", "deactivate_tests")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Основная информация", {"fields": ("title", "description", "level", "subject", "is_active")}),
        ("Системная информация", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    class Media:
        css = ADMIN_CSS
        js = ("testing/admin/test_questions.js",)

    def get_fieldsets(self, request, obj=None):
        # Timestamps only exist once the test is saved.
        return self.fieldsets if obj is not None else self.fieldsets[:1]

    def get_queryset(self, request):
        # One COUNT per page instead of one per row; same number as
        # Test.question_count, which the column falls back to.
        return super().get_queryset(request).annotate(questions_total=Count("questions"))

    # -- columns ---------------------------------------------------------

    @admin.display(description="Уровень", ordering="level")
    def level_badge(self, obj: Test) -> str:
        return difficulty_badge(obj.level)

    @admin.display(description="Статус", ordering="is_active")
    def status_badge(self, obj: Test) -> str:
        return active_badge(obj.is_active)

    @admin.display(description="Кол-во вопросов", ordering="questions_total")
    def question_count_display(self, obj: Test) -> str:
        count = getattr(obj, "questions_total", None)
        return question_count_label(obj.question_count if count is None else count)

    @admin.display(description="Создан", ordering="created_at")
    def created_display(self, obj: Test) -> str:
        return _created_display(obj.created_at)

    # -- bulk actions ----------------------------------------------------

    @admin.action(description="Активировать выбранные", permissions=["change"])
    def activate_tests(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Активировано: {_tests_label(updated)}.", messages.SUCCESS)

    @admin.action(description="Деактивировать выбранные", permissions=["change"])
    def deactivate_tests(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Деактивировано: {_tests_label(updated)}.", messages.SUCCESS)

    # -- change page: questions block -------------------------------------

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        if obj is not None and not obj._state.adding:
            questions = list(
                obj.questions.annotate(options_total=Count("options")).order_by("order", "created_at")
            )
            can_change_question = request.user.has_perm("testing.change_question")
            context.update(
                test_questions=questions,
                test_question_count=len(questions),
                can_add_question=request.user.has_perm("testing.add_question"),
                can_change_question=can_change_question,
                can_reorder_questions=can_change_question and self.has_change_permission(request, obj),
                from_test_query=f"{FROM_TEST_PARAM}={FROM_TEST_VALUE}",
            )
        return super().render_change_form(request, context, add, change, form_url, obj)

    def get_urls(self):
        info = self.opts.app_label, self.opts.model_name
        return [
            path(
                "<path:object_id>/questions/reorder/",
                self.admin_site.admin_view(self.reorder_questions_view),
                name="%s_%s_reorder_questions" % info,
            ),
        ] + super().get_urls()

    def reorder_questions_view(self, request, object_id):
        """Persist a drag & drop order: POST {"order": [question ids]} →
        Question.order = 1..n. The list must be exactly this test's current
        questions, so a stale page can't silently drop or misplace any."""
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        test = self.get_object(request, unquote(object_id))
        if test is None:
            return JsonResponse({"error": "Тест не найден."}, status=404)
        if not (self.has_change_permission(request, test) and request.user.has_perm("testing.change_question")):
            raise PermissionDenied

        try:
            ids = json.loads(request.body or b"{}").get("order")
        except (ValueError, AttributeError):
            ids = None
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            return JsonResponse({"error": "Некорректный запрос."}, status=400)

        with transaction.atomic():
            questions = {str(q.pk): q for q in test.questions.select_for_update()}
            if len(ids) != len(set(ids)) or set(ids) != set(questions):
                return JsonResponse(
                    {"error": "Список вопросов изменился — обновите страницу и попробуйте снова."}, status=409
                )
            for position, question_id in enumerate(ids, start=1):
                questions[question_id].order = position
            Question.objects.bulk_update(questions.values(), ["order"])
        return JsonResponse({"ok": True, "count": len(ids)})


def _tests_label(n: int) -> str:
    return f"{n} {plural_ru(n, 'тест', 'теста', 'тестов')}"


# ---------------------------------------------------------------------------
# Question / QuestionOption
# ---------------------------------------------------------------------------

class QuestionOptionFormSet(forms.BaseInlineFormSet):
    """Choice questions need options with a correct answer; text/code
    questions must not carry options (they would never be shown)."""

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        active = [
            form for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE")
        ]
        question_type = self.instance.question_type
        if question_type in CHOICE_TYPES:
            if len(active) < 2:
                raise ValidationError("Добавьте минимум два варианта ответа.")
            correct = sum(1 for form in active if form.cleaned_data.get("is_correct"))
            if not correct:
                raise ValidationError("Отметьте хотя бы один правильный вариант.")
            if question_type == QuestionType.SINGLE_CHOICE and correct > 1:
                raise ValidationError("Для типа «Один вариант» правильным может быть только один вариант.")
        elif active:
            raise ValidationError(
                f"Для типа «{QuestionType(question_type).label}» варианты ответа не нужны — "
                "отметьте их на удаление."
            )


class QuestionOptionForm(forms.ModelForm):
    class Meta:
        model = QuestionOption
        fields = ("text", "is_correct", "order")

    def has_changed(self):
        # Empty rows come with a prefilled «Порядок» (initial data on GET,
        # question_form.js for added rows); that alone must not turn a blank
        # row into a filled one that fails «обязательное поле».
        if self.instance._state.adding and not self.data.get(self.add_prefix("text"), "").strip() \
                and not self.data.get(self.add_prefix("is_correct")):
            return False
        return super().has_changed()


class QuestionOptionInline(admin.TabularInline):
    model = QuestionOption
    form = QuestionOptionForm
    formset = QuestionOptionFormSet
    fields = ("text", "is_correct", "order")
    # verbose_name feeds Django's «Добавить еще один …» link text.
    verbose_name = "вариант"
    verbose_name_plural = "Варианты ответа"
    classes = ("ok-question-options",)

    def get_extra(self, request, obj=None, **kwargs):
        if obj is not None and not obj._state.adding and obj.options.exists():
            return 0
        return 4


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = (
        "short_text", "test", "type_display", "difficulty_badge_display",
        "language_display", "order", "created_display",
    )
    list_display_links = ("short_text",)
    list_editable = ("order",)
    list_filter = ("test", "question_type", "difficulty", "language")
    list_select_related = ("test",)
    search_fields = ("text", "test__title")
    search_help_text = "Текст вопроса или название теста"
    list_per_page = 50
    autocomplete_fields = ("test",)
    actions = ("set_difficulty_easy", "set_difficulty_medium", "set_difficulty_hard")
    inlines = (QuestionOptionInline,)
    # Question.metadata (import bookkeeping) is left out on purpose; fields
    # missing from the form keep their stored value on save.
    fields = ("test", "text", "question_type", "difficulty", "language", "order")

    class Media:
        css = ADMIN_CSS
        js = ("testing/admin/question_form.js",)

    # -- columns ---------------------------------------------------------

    @admin.display(description="Вопрос", ordering="text")
    def short_text(self, obj: Question) -> str:
        text = " ".join(obj.text.split())
        return text if len(text) <= 90 else f"{text[:89]}…"

    @admin.display(description="Тип", ordering="question_type")
    def type_display(self, obj: Question) -> str:
        return obj.get_question_type_display()

    @admin.display(description="Сложность", ordering="difficulty")
    def difficulty_badge_display(self, obj: Question) -> str:
        return difficulty_badge(obj.difficulty)

    @admin.display(description="Язык", ordering="language")
    def language_display(self, obj: Question) -> str:
        return obj.get_language_display() or "—"

    @admin.display(description="Создан", ordering="created_at")
    def created_display(self, obj: Question) -> str:
        return _created_display(obj.created_at)

    # -- bulk actions ----------------------------------------------------

    def _set_difficulty(self, request, queryset, level: DifficultyLevel):
        updated = queryset.update(difficulty=level)
        self.message_user(
            request, f"Сложность «{level.label}» установлена для: {question_count_label(updated)}.", messages.SUCCESS
        )

    @admin.action(description="Изменить сложность → Лёгкий", permissions=["change"])
    def set_difficulty_easy(self, request, queryset):
        self._set_difficulty(request, queryset, DifficultyLevel.EASY)

    @admin.action(description="Изменить сложность → Средний", permissions=["change"])
    def set_difficulty_medium(self, request, queryset):
        self._set_difficulty(request, queryset, DifficultyLevel.MEDIUM)

    @admin.action(description="Изменить сложность → Сложный", permissions=["change"])
    def set_difficulty_hard(self, request, queryset):
        self._set_difficulty(request, queryset, DifficultyLevel.HARD)

    def get_actions(self, request):
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            func, name, _ = actions["delete_selected"]
            actions["delete_selected"] = (func, name, "Удалить выбранные")
        return actions

    # -- form ------------------------------------------------------------

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        test_id = initial.get("test")
        if test_id and "order" not in initial:
            try:
                last = Question.objects.filter(test_id=test_id).aggregate(last=Max("order"))["last"]
            except (ValueError, ValidationError):
                last = None
            initial["order"] = (last or 0) + 1
        return initial

    def get_formset_kwargs(self, request, obj, inline, prefix):
        kwargs = super().get_formset_kwargs(request, obj, inline, prefix)
        if isinstance(inline, QuestionOptionInline) and request.method == "GET":
            # Number the empty option rows after the existing ones (1, 2, 3…).
            start = 0
            if obj is not None and not obj._state.adding:
                start = obj.options.aggregate(last=Max("order"))["last"] or 0
            kwargs["initial"] = [{"order": start + i} for i in range(1, inline.get_extra(request, obj) + 1)]
        return kwargs

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        parent_test = obj.test if obj is not None and obj.test_id else None
        if parent_test is None:
            test_id = context["adminform"].form.initial.get("test")
            parent_test = Test.objects.filter(pk=test_id).first() if _is_uuid(test_id) else None
        context.update(
            parent_test=parent_test,
            choice_types=",".join(CHOICE_TYPES),
            code_type=QuestionType.CODE,
        )
        return super().render_change_form(request, context, add, change, form_url, obj)

    # -- redirects back to the test page ------------------------------------

    def _from_test(self, request) -> bool:
        return request.GET.get(FROM_TEST_PARAM) == FROM_TEST_VALUE and "_popup" not in request.POST

    def _back_to_test(self, request, obj: Question):
        if "_addanother" in request.POST:
            url = reverse("admin:testing_question_add")
            return HttpResponseRedirect(f"{url}?test={obj.test_id}&{FROM_TEST_PARAM}={FROM_TEST_VALUE}")
        url = reverse("admin:testing_test_change", args=[obj.test_id])
        return HttpResponseRedirect(f"{url}#questions")

    def response_add(self, request, obj, post_url_continue=None):
        response = super().response_add(request, obj, post_url_continue)
        if self._from_test(request) and "_continue" not in request.POST:
            return self._back_to_test(request, obj)
        return response

    def response_change(self, request, obj):
        response = super().response_change(request, obj)
        if self._from_test(request) and "_continue" not in request.POST and "_saveasnew" not in request.POST:
            return self._back_to_test(request, obj)
        return response


def _is_uuid(value) -> bool:
    try:
        return bool(value) and Test._meta.pk.to_python(value) is not None
    except ValidationError:
        return False
