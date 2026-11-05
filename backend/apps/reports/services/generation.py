"""One click → a stored report: calculation snapshot, texts and PNG images.

    request = ReportRequest(period=periods.resolve("this_month", today=...), report_type="group", ...)
    report = generate(group, request, user=request.user, teacher=None)

Nothing is overwritten: every call creates a new ParentReport row. When the
PNG cannot be rendered (e.g. no Chromium on the server) the report is still
stored with its snapshot and texts, status «partial» and the reason in
``error`` — the trainer can copy the text and regenerate later.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import logging

from django.core.files.base import ContentFile
from django.utils import timezone

from apps.academy.models import Group

from ..models import ParentReport, ParentReportImage
from . import analytics, image_generator, recommendations, text_generator
from .periods import ReportPeriod, resolve

logger = logging.getLogger(__name__)

DEFAULT_OPTIONS = {
    "include_table": True,
    "include_group_stats": True,
    "include_recommendations": True,
    "include_comparison": True,
}


@dataclasses.dataclass
class ReportRequest:
    period: ReportPeriod
    report_type: str = ParentReport.ReportType.GROUP
    language: str = ParentReport.Language.RU
    output_format: str = ParentReport.OutputFormat.BOTH
    options: dict = dataclasses.field(default_factory=lambda: dict(DEFAULT_OPTIONS))
    student_ids: list[int] | None = None

    @property
    def wants_image(self) -> bool:
        return self.output_format in (ParentReport.OutputFormat.PNG, ParentReport.OutputFormat.BOTH)

    @property
    def wants_text(self) -> bool:
        return self.output_format in (ParentReport.OutputFormat.TEXT, ParentReport.OutputFormat.BOTH)

    def stored_options(self) -> dict:
        return {**DEFAULT_OPTIONS, **self.options, "student_ids": self.student_ids}


def request_from_report(report: ParentReport, *, today: dt.date) -> ReportRequest:
    """The same request again — «Перегенерировать» recalculates the same period."""
    # The stored dates are recalculated — a «last month» report stays that
    # month, never shifted to today's «last month» — against the same
    # comparison period.
    period = resolve("custom", today=today, start_date=report.start_date, end_date=report.end_date)
    period = dataclasses.replace(period, key=report.period_key, previous=_stored_previous(report, period))
    options = {key: report.options.get(key, default) for key, default in DEFAULT_OPTIONS.items()}
    return ReportRequest(
        period=period,
        report_type=report.report_type,
        language=report.language,
        output_format=report.output_format,
        options=options,
        student_ids=report.options.get("student_ids"),
    )


def _stored_previous(report: ParentReport, period: ReportPeriod):
    from apps.academy.services.analytics.period import DateRange

    if report.compare_start_date and report.compare_end_date:
        return DateRange(report.compare_start_date, report.compare_end_date)
    return period.previous


def build_preview(group: Group, request: ReportRequest, *, teacher_id: int | None, today: dt.date | None = None) -> dict:
    """Everything a report would contain — without storing or rendering anything."""
    snapshot = analytics.build_report_data(
        group, request.period, teacher_id=teacher_id, today=today, student_ids=request.student_ids,
    )
    return {
        "snapshot": snapshot,
        **texts_for(snapshot, request),
        "recommendations": recommendations_for(snapshot, request),
    }


def texts_for(snapshot: dict, request: ReportRequest) -> dict:
    options = request.stored_options()
    if request.report_type == ParentReport.ReportType.STUDENTS:
        return {"text": "", "student_texts": text_generator.student_messages(snapshot, language=request.language, options=options)}
    return {"text": text_generator.group_message(snapshot, language=request.language, options=options), "student_texts": {}}


def recommendations_for(snapshot: dict, request: ReportRequest) -> dict:
    with_comparison = request.options.get("include_comparison", True)
    language = request.language
    return {
        "group": recommendations.build(
            recommendations.facts_for_group(snapshot, include_comparison=with_comparison), scope="group", language=language,
        ),
        "students": {
            str(entry["id"]): recommendations.build(
                recommendations.facts_for_student(entry, include_comparison=with_comparison),
                scope="student", language=language,
            )
            for entry in snapshot["students"]
        },
    }


def generate(
    group: Group,
    request: ReportRequest,
    *,
    user,
    teacher=None,
    today: dt.date | None = None,
    regenerated_from: ParentReport | None = None,
) -> ParentReport:
    today = today or timezone.localdate()
    teacher_id = teacher.pk if teacher is not None else None
    snapshot = analytics.build_report_data(
        group, request.period, teacher_id=teacher_id, today=today, student_ids=request.student_ids,
    )
    texts = texts_for(snapshot, request) if request.wants_text else {"text": "", "student_texts": {}}

    report = ParentReport.objects.create(
        group=group,
        group_name=group.name,
        course_name=snapshot["group"]["course"],
        report_type=request.report_type,
        language=request.language,
        output_format=request.output_format,
        period_key=request.period.key,
        start_date=request.period.current.start,
        end_date=request.period.current.end,
        compare_start_date=request.period.previous.start,
        compare_end_date=request.period.previous.end,
        options=request.stored_options(),
        snapshot=snapshot,
        text=texts["text"],
        student_texts=texts["student_texts"],
        status=ParentReport.Status.READY,
        teacher_scope=teacher,
        created_by=user if getattr(user, "is_authenticated", False) else None,
        regenerated_from=regenerated_from,
    )
    if request.wants_image:
        _render_images(report, snapshot, request)
    return report


def _render_images(report: ParentReport, snapshot: dict, request: ReportRequest) -> None:
    options = request.stored_options()
    try:
        if request.report_type == ParentReport.ReportType.STUDENTS:
            rendered = image_generator.render_student_reports(snapshot, language=request.language, options=options)
            for index, (entry, page) in enumerate(rendered, start=1):
                _save_image(report, page, index, entry)
        else:
            for index, page in enumerate(
                image_generator.render_group_report(snapshot, language=request.language, options=options), start=1,
            ):
                _save_image(report, page, index, None)
    except image_generator.ImageGenerationError as exc:
        report.images.all().delete()
        report.status = ParentReport.Status.PARTIAL
        report.error = str(exc)
        report.save(update_fields=["status", "error"])


def _save_image(report: ParentReport, page, index: int, entry: dict | None) -> ParentReportImage:
    if entry is not None:
        filename = f"student-{entry['id']}.png"
    else:
        filename = f"group-page-{index}.png"
    image = ParentReportImage(
        report=report,
        student_id=entry["id"] if entry else None,
        student_name=entry["name"] if entry else "",
        page=index,
        width=page.width,
        height=page.height,
    )
    image.image.save(filename, ContentFile(page.png), save=False)
    image.save()
    return image
