"""Student & Parent Portal API — /api/v1/portal/.

Every view requires an authenticated STUDENT_PARENT account (IsPortalUser)
and resolves `student_id` only among the students linked to that account
(services.scope.get_student → 404 for anyone else's id). The isolation
middleware (apps.portal.access) additionally keeps these accounts out of
every other API and holds them on the password change until the temporary
password is replaced.
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
from .serializers import HomeworkSubmitSerializer, PasswordChangeSerializer
from .services import accounts, data, report_pdf, reports, scope

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
class HomeworkDetailView(PortalView):
    def get(self, request, student_id, homework_id):
        homework, result = data.homework_for(self.student(student_id), homework_id)
        return Response(data.homework_row(homework, result, self.today(), full=True))


@extend_schema(tags=TAGS, request=HomeworkSubmitSerializer, responses={200: dict})
class HomeworkSubmitView(PortalView):
    def post(self, request, student_id, homework_id):
        student = self.student(student_id)
        serializer = HomeworkSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            homework, result = data.submit_homework(student, homework_id, user=request.user, **serializer.validated_data)
        except DjangoValidationError as exc:
            raise _drf_error(exc)
        return Response(data.homework_row(homework, result, self.today(), full=True))


@extend_schema(tags=TAGS, responses={200: dict})
class AttendanceView(PortalView):
    def get(self, request, student_id):
        student = self.student(student_id)
        try:
            year, month = data.parse_month(request.query_params, today=self.today())
        except DjangoValidationError as exc:
            raise _drf_error(exc)
        return Response(data.attendance_month(student, year, month))


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
class PaymentsView(PortalView):
    def get(self, request, student_id):
        student = self.student(student_id)
        if not self.account().can_view_payments:
            raise PermissionDenied("Информация об оплате для этого аккаунта скрыта.")
        return Response(data.payments(student))


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
