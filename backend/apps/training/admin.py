"""«Тренировочный портал» in the Django admin.

* «Тренажёры» — a trainer is a training session of a test (proxy model
  Trainer). One form edits the trainer and the test settings behind it;
  questions are edited in the test's question editor («Вопросы»).
  Publish / unpublish / archive from the list.
* «Попытки тренажёров» — read-only; an attempt opens on its page with
  answers and the event log.
* «Настройки портала», «Видео», «Полезные ссылки».
"""
from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html

from apps.testing.admin import AdminRoleOnly
from apps.testing.models import SessionType, Test, TestStatus
from apps.users.models import Subject

from .models import PortalSettings, Trainer, TrainerStatus, TrainingAttempt, TrainingLink, TrainingVideo

# Test fields edited from the trainer form, in display order.
TEST_FIELDS = {
    "description": forms.CharField(label="Описание", required=False, widget=forms.Textarea(attrs={"rows": 3})),
    "subject": forms.ModelChoiceField(label="Предмет", queryset=Subject.objects.order_by("name"), required=False),
    "image_url": forms.URLField(label="Обложка (URL)", required=False, max_length=1000),
    "questions_per_attempt": forms.IntegerField(
        label="Количество вопросов", required=False, min_value=1,
        help_text="Пусто — все вопросы теста; иначе случайная выборка такого размера.",
    ),
    "passing_score": forms.IntegerField(label="Проходной балл, %", min_value=0, max_value=100, initial=60),
    "show_correct_answers": forms.BooleanField(label="Показывать правильный ответ и пояснение", required=False, initial=True),
    "show_result": forms.BooleanField(label="Показывать результат", required=False, initial=True),
    "allow_retry": forms.BooleanField(label="Разрешить повторное прохождение", required=False, initial=True),
    "shuffle_questions": forms.BooleanField(label="Перемешивать вопросы", required=False),
    "shuffle_options": forms.BooleanField(label="Перемешивать варианты", required=False),
    "require_fullscreen": forms.BooleanField(label="Обязательный полноэкранный режим", required=False,
                                             help_text="Выход из полноэкранного режима фиксируется, тест закрывается оверлеем до возврата."),
    "track_tab_switches": forms.BooleanField(label="Отслеживать уход со страницы", required=False, initial=True),
    "max_tab_switches": forms.IntegerField(label="Допустимо уходов со страницы", required=False, min_value=0, max_value=100,
                                           help_text="Следующий уход завершает попытку. Пусто — только фиксировать."),
    "block_copy_paste": forms.BooleanField(label="Запрет копирования и вставки", required=False, initial=True),
}


class TrainerForm(forms.ModelForm):
    class Meta:
        model = Trainer
        fields = ("title", "test", "course", "group", "time_limit_minutes", "max_attempts_per_student", "exam_url")
        labels = {"title": "Название", "test": "Тест (вопросы)", "time_limit_minutes": "Время, мин",
                  "max_attempts_per_student": "Попыток на одно имя"}
        help_texts = {
            "test": "Существующий тест с вопросами. Пусто — будет создан новый тест с этим названием; вопросы добавьте после сохранения («Вопросы»).",
            "group": "Необязательно: преподаватели этой группы увидят попытки в мониторинге.",
            "time_limit_minutes": "Пусто — время из теста (или без ограничения).",
            "max_attempts_per_student": "Пусто — без ограничений.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.users.models import Subject

        self.instance.session_type = SessionType.TRAINING  # validated as a trainer, never as an exam

        self.fields["test"].required = False
        self.fields["title"].required = True
        for name, field in TEST_FIELDS.items():
            if name == "subject":
                field = forms.ModelChoiceField(label="Предмет", queryset=Subject.objects.order_by("name"), required=False)
            self.fields[name] = field
        test = self.instance.test if self.instance.pk and self.instance.test_id else None
        if test is not None:
            for name in TEST_FIELDS:
                self.initial[name] = getattr(test, f"{name}_id" if name == "subject" else name)

    def clean(self):
        data = super().clean()
        if not data.get("test") and data.get("title") and Test.objects.filter(title=data["title"].strip()).exists():
            self.add_error("test", "Тест с таким названием уже есть — выберите его здесь или измените название.")
        return data

    def save(self, commit=True):
        trainer = super().save(commit=False)
        data = self.cleaned_data
        test = data.get("test") or Test(title=data["title"].strip(), status=TestStatus.DRAFT)
        for name in TEST_FIELDS:
            value = data.get(name)
            if name in ("description", "image_url"):
                value = value or ""
            setattr(test, name, value)
        test.save()
        trainer.test = test
        if commit:
            trainer.save()
        return trainer


# The test's settings are declared form fields (the admin's fieldsets need
# them at class level); they are read from / written to trainer.test.
TrainerForm.declared_fields.update(TEST_FIELDS)
TrainerForm.base_fields.update(TEST_FIELDS)


class AdminRoleOnlyMixin(AdminRoleOnly):
    pass


@admin.register(Trainer)
class TrainerAdmin(AdminRoleOnlyMixin, admin.ModelAdmin):
    form = TrainerForm
    list_display = ("title_column", "subject_column", "questions_column", "attempts_column", "status_badge", "links")
    list_filter = ("is_public", "status", "test__subject", "course")
    search_fields = ("title", "test__title")
    actions = ["publish", "unpublish", "archive"]
    readonly_fields = ("status_badge", "links")
    fieldsets = (
        ("Основная информация", {"fields": ("title", "test", "description", "subject", "course", "group", "image_url", "status_badge", "links")}),
        ("Настройки теста", {"fields": ("questions_per_attempt", "time_limit_minutes", "passing_score", "show_correct_answers",
                                        "show_result", "allow_retry", "max_attempts_per_student", "shuffle_questions", "shuffle_options")}),
        ("Безопасность", {"fields": ("require_fullscreen", "track_tab_switches", "max_tab_switches", "block_copy_paste"),
                          "description": "Браузер не позволяет запретить другие вкладки или устройства: система предотвращает, "
                                         "что может, фиксирует действия и показывает их в мониторинге."}),
        ("Настоящий экзамен", {"fields": ("exam_url",)}),
    )

    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .select_related("test__subject", "course")
            .annotate(question_total=Count("test__questions", distinct=True), attempt_total=Count("attempts", distinct=True))
        )

    @admin.display(description="Тренажёр", ordering="title")
    def title_column(self, obj):
        return obj.title or obj.test.title

    @admin.display(description="Предмет")
    def subject_column(self, obj):
        return obj.test.subject.name if obj.test.subject_id else "—"

    @admin.display(description="Вопросов")
    def questions_column(self, obj):
        return getattr(obj, "question_total", obj.test.questions.count())

    @admin.display(description="Попыток")
    def attempts_column(self, obj):
        return getattr(obj, "attempt_total", obj.attempts.count())

    @admin.display(description="Статус")
    def status_badge(self, obj):
        if not obj.pk:
            return "—"
        status = obj.trainer_status
        color = {TrainerStatus.PUBLISHED: "success", TrainerStatus.DRAFT: "secondary", TrainerStatus.ARCHIVED: "dark"}[status]
        return format_html('<span class="badge bg-{}">{}</span>', color, TrainerStatus(status).label)

    @admin.display(description="Действия")
    def links(self, obj):
        if not obj.pk:
            return "—"
        parts = [format_html(
            '<a class="btn btn-sm btn-outline-primary" href="{}"><i class="bi bi-list-check"></i> Вопросы</a>',
            reverse("admin:testing_test_change", args=[obj.test_id]),
        ), format_html(
            '<a class="btn btn-sm btn-outline-secondary" href="{}"><i class="bi bi-bar-chart"></i> Результаты</a>',
            reverse("admin:testing_session_analytics", args=[obj.pk]),
        )]
        base = PortalSettings.load().portal_url.rstrip("/")
        if base:
            parts.append(format_html(
                '<a class="btn btn-sm btn-outline-success" target="_blank" rel="noopener" href="{}/training/{}"><i class="bi bi-box-arrow-up-right"></i> Открыть тренажёр</a>',
                base, obj.pk,
            ))
        return format_html(" ".join(["{}"] * len(parts)), *parts)

    def _bulk(self, request, queryset, method, done):
        ok = 0
        for trainer in queryset:
            try:
                getattr(trainer, method)()
                ok += 1
            except ValidationError as exc:
                messages.error(request, f"«{trainer.title or trainer.test.title}»: {exc.messages[0]}")
        if ok:
            messages.success(request, f"{done}: {ok}.")

    @admin.action(description="Опубликовать")
    def publish(self, request, queryset):
        self._bulk(request, queryset, "publish", "Опубликовано")

    @admin.action(description="Снять с публикации (в черновик)")
    def unpublish(self, request, queryset):
        self._bulk(request, queryset, "unpublish", "Снято с публикации")

    @admin.action(description="В архив")
    def archive(self, request, queryset):
        self._bulk(request, queryset, "archive", "В архиве")

    def response_add(self, request, obj, post_url_continue=None):
        messages.info(request, "Тренажёр создан как черновик. Добавьте вопросы («Вопросы»), затем опубликуйте.")
        return super().response_add(request, obj, post_url_continue)


@admin.register(TrainingAttempt)
class TrainingAttemptAdmin(AdminRoleOnlyMixin, admin.ModelAdmin):
    list_display = ("student_name", "trainer_column", "started_at", "finished_at", "status", "score_column",
                    "tab_switch_count", "violation_count", "open_link")
    list_filter = ("status", "finish_reason", "session__test__subject")
    search_fields = ("student_name", "session__title", "session__test__title")
    date_hierarchy = "started_at"
    list_select_related = ("session__test",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="Тренажёр")
    def trainer_column(self, obj):
        return obj.session.title or obj.session.test.title

    @admin.display(description="Балл")
    def score_column(self, obj):
        return f"{round(obj.score)}%" if obj.status == "finished" else "—"

    @admin.display(description="")
    def open_link(self, obj):
        return format_html('<a href="{}">Ответы и журнал</a>', reverse("admin:testing_attempt_detail", args=[obj.pk]))


@admin.register(PortalSettings)
class PortalSettingsAdmin(AdminRoleOnlyMixin, admin.ModelAdmin):
    fieldsets = (
        ("Главная страница", {"fields": ("hero_title", "hero_subtitle", "start_button_label")}),
        ("Настоящий экзамен", {"fields": ("exam_button_label", "exam_url", "exam_open_in_new_tab")}),
        ("Портал", {"fields": ("portal_url",)}),
    )

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not PortalSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # One row: the list goes straight to its form.
        return redirect(reverse("admin:training_portalsettings_change", args=[PortalSettings.load().pk]))


class _OrderedContentAdmin(AdminRoleOnlyMixin, admin.ModelAdmin):
    list_display = ("title", "category", "order", "published", "updated_at")
    list_editable = ("order", "published")
    list_filter = ("published", "category")
    search_fields = ("title", "description", "category")
    actions = ["publish", "unpublish"]

    @admin.action(description="Опубликовать")
    def publish(self, request, queryset):
        queryset.update(published=True)

    @admin.action(description="Снять с публикации")
    def unpublish(self, request, queryset):
        queryset.update(published=False)


@admin.register(TrainingVideo)
class TrainingVideoAdmin(_OrderedContentAdmin):
    list_display = ("title", "category", "duration", "link", "order", "published", "updated_at")
    fields = ("title", "description", "video_url", "thumbnail_url", "category", "duration", "order", "published")

    @admin.display(description="Видео")
    def link(self, obj):
        return format_html('<a href="{}" target="_blank" rel="noopener noreferrer">открыть</a>', obj.video_url)


@admin.register(TrainingLink)
class TrainingLinkAdmin(_OrderedContentAdmin):
    fields = ("title", "description", "url", "category", "icon", "order", "published")
