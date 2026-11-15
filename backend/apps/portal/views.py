"""Student & Parent Portal API — /api/v1/portal/.

Every view requires an authenticated STUDENT_PARENT account (IsPortalUser)
and resolves `student_id` only among the students linked to that account
(services.scope.get_student → 404 for anyone else's id). The isolation
middleware (apps.portal.access) additionally keeps these accounts out of
every other API and holds them on the password change until the temporary
password is replaced.

Homework is read-only here: it is done outside the LMS and checked offline
by the trainer, who records status / grade / comment in the existing grading
form (HomeworkViewSet.results → services.homework_service). The portal only
shows what was saved there.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .access import is_portal_user
from .models import PortalAccount
from .serializers import PasswordChangeSerializer
from .services import accounts, attendance, data, finance, gamification, report_pdf, reports, scope

TAGS = ["Student & Parent Portal"]


class IsPortalUser(BasePermission):
    message = "Раздел доступен только в кабинете ученика и родителя."

    def has_permission(self, request, view) -> bool:
        return bool(is_portal_user(request.user) and request.user.is_active)


def _drf_error(exc: DjangoValidationError) -> DRFValidationError:
    if hasattr(exc, "error_dict"):
        return DRFValidationError({key: DjangoValidationError(value).messages for key, value in exc.error_dict.items()})
    return DRFValidationError({"detail": exc.messages})


class _Pagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class PortalView(APIView):
    permission_classes = [IsAuthenticated, IsPortalUser]

    def account(self) -> PortalAccount:
        account = getattr(self.request.user, "portal_account", None)
        if account is None:
            raise PermissionDenied("Аккаунт кабинета не настроен.")
        return account

    def student(self, student_id):
        return scope.get_student(self.request.user, student_id)

    @staticmethod
    def today():
        return timezone.localdate()


@extend_schema(tags=TAGS, responses={200: dict})
class MeView(PortalView):
    def get(self, request):
        account = self.account()
        return Response({
            "login": request.user.username,
            "must_change_password": account.must_change_password,
            "can_view_payments": account.can_view_payments,
            "students": [data.student_card(s) for s in scope.linked_students(request.user)],
        })


@extend_schema(tags=TAGS, request=PasswordChangeSerializer, responses={200: dict})
class PasswordChangeView(PortalView):
    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            accounts.change_own_password(
                request.user, current_password=serializer.validated_data["current_password"],
                new_password=serializer.validated_data["new_password"],
            )
        except DjangoValidationError as exc:
            raise _drf_error(exc)
        return Response({"must_change_password": False})


@extend_schema(tags=TAGS, responses={200: dict})
class DashboardView(PortalView):
    def get(self, request, student_id):
        return Response(data.dashboard(self.student(student_id), today=self.today(),
                                       can_view_payments=self.account().can_view_payments))


@extend_schema(tags=TAGS, responses={200: dict})
class ScheduleView(PortalView):
    def get(self, request, student_id):
        student = self.student(student_id)
        try:
            start, end = data.parse_range(request.query_params.get("start"), request.query_params.get("end"),
                                          today=self.today())
        except DjangoValidationError as exc:
            raise _drf_error(exc)
        return Response(data.schedule(student, start, end))


@extend_schema(tags=TAGS, responses={200: dict})
class HomeworkListView(PortalView):
    def get(self, request, student_id):
        rows = data.homework_list(self.student(student_id), state=request.query_params.get("state"),
                                  today=self.today())
        paginator = _Pagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        return paginator.get_paginated_response(page)


@extend_schema(tags=TAGS, responses={200: dict})
class NextHomeworkView(PortalView):
    """The homework of the student's next scheduled lesson (one per program)."""

    def get(self, request, student_id):
        return Response(data.next_homework(self.student(student_id), today=self.today()))


@extend_schema(tags=TAGS, responses={200: dict})
class HomeworkDetailView(PortalView):
    def get(self, request, student_id, homework_id):
        homework, result = data.homework_for(self.student(student_id), homework_id, self.today())
        return Response(data.homework_row(homework, result, self.today(), full=True))


@extend_schema(tags=TAGS, responses={200: dict})
class AttendanceView(PortalView):
    def get(self, request, student_id):
        student = self.student(student_id)
        try:
            year, month = data.parse_month(request.query_params, today=self.today())
        except DjangoValidationError as exc:
            raise _drf_error(exc)
        return Response(attendance.calendar(student, year, month, today=self.today()))


@extend_schema(tags=TAGS, responses={200: dict})
class AttendanceOverviewView(PortalView):
    def get(self, request, student_id):
        return Response(attendance.overview(self.student(student_id), today=self.today()))


@extend_schema(tags=TAGS, responses={200: dict})
class AttendanceHistoryView(PortalView):
    def get(self, request, student_id):
        student = self.student(student_id)
        status_ = request.query_params.get("status") or "all"
        if status_ != "all" and status_ not in attendance.STATUSES:
            raise DRFValidationError({"status": "Допустимо: all, " + ", ".join(attendance.STATUSES) + "."})
        paginator = _Pagination()
        page = paginator.paginate_queryset(attendance.history(student, status=status_, today=self.today()), request, view=self)
        return paginator.get_paginated_response([attendance.history_row(r, student.branch) for r in page])


@extend_schema(tags=TAGS, responses={200: dict})
class NotificationsView(PortalView):
    def get(self, request, student_id):
        return Response({"results": data.notifications(
            self.student(student_id), today=self.today(), can_view_payments=self.account().can_view_payments,
        )})


@extend_schema(tags=TAGS, responses={200: dict})
class FeedbackView(PortalView):
    def get(self, request, student_id):
        return Response({"results": data.teacher_feedback(self.student(student_id), limit=50)})


@extend_schema(tags=TAGS, responses={200: dict})
class AchievementsView(PortalView):
    def get(self, request, student_id):
        return Response(gamification.overview(self.student(student_id), today=self.today()))


@extend_schema(tags=TAGS, responses={200: dict})
class _FinanceView(PortalView):
    """Read-only accounting data of a linked student — only for accounts the
    school lets see payments (PortalAccount.can_view_payments)."""

    def finance_student(self, student_id):
        student = self.student(student_id)
        if not self.account().can_view_payments:
            raise PermissionDenied("Информация об оплате для этого аккаунта скрыта.")
        return student


class PaymentsView(_FinanceView):
    def get(self, request, student_id):
        return Response(finance.overview(self.finance_student(student_id), today=self.today()))


@extend_schema(tags=TAGS, responses={200: dict})
class PaymentTransactionsView(_FinanceView):
    def get(self, request, student_id):
        student = self.finance_student(student_id)
        status_ = request.query_params.get("status") or "all"
        if status_ not in finance.TRANSACTION_FILTERS:
            raise DRFValidationError({"status": f"Допустимо: {', '.join(finance.TRANSACTION_FILTERS)}."})
        return Response({"results": finance.transactions(student, status=status_)})


@extend_schema(tags=TAGS, responses={200: dict})
class PaymentDocumentsView(_FinanceView):
    def get(self, request, student_id):
        return Response(finance.documents(self.finance_student(student_id), today=self.today()))


@extend_schema(tags=TAGS, responses={200: dict})
class ReceiptDetailView(_FinanceView):
    def get(self, request, student_id, receipt_id):
        receipt = finance.get_receipt(self.finance_student(student_id), receipt_id)
        return Response(finance.receipt_row(receipt, full=True))


@extend_schema(tags=TAGS, responses={200: bytes})
class ReceiptPdfView(_FinanceView):
    """The receipt document exactly as the accounting system renders it.
    `?download=1` → attachment, otherwise inline (preview / print)."""

    def get(self, request, student_id, receipt_id):
        receipt = finance.get_receipt(self.finance_student(student_id), receipt_id)
        content = finance.receipt_pdf(receipt, compact=request.query_params.get("size") == "compact")
        response = HttpResponse(content, content_type="application/pdf")
        disposition = "attachment" if request.query_params.get("download") in ("1", "true") else "inline"
        response["Content-Disposition"] = f'{disposition}; filename="receipt-{receipt.number or receipt.pk}.pdf"'
        response["Cache-Control"] = "private, no-store"
        return response


def _report(view: PortalView, student_id):
    student = view.student(student_id)
    try:
        year, month = data.parse_month(view.request.query_params, today=view.today())
        return reports.monthly_report(student, year, month, today=view.today())
    except DjangoValidationError as exc:
        raise _drf_error(exc)


@extend_schema(tags=TAGS, responses={200: dict})
class MonthlyReportView(PortalView):
    def get(self, request, student_id):
        return Response(_report(self, student_id))


@extend_schema(tags=TAGS, responses={200: bytes})
class MonthlyReportPdfView(PortalView):
    def get(self, request, student_id):
        report = _report(self, student_id)
        lang = request.query_params.get("lang", "ru")
        response = HttpResponse(report_pdf.render(report, lang), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{report_pdf.pdf_filename(report)}"'
        response["Cache-Control"] = "private, no-store"
        return response
