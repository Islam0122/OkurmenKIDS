from django.apps import AppConfig


class AttendanceMatrixConfig(AppConfig):
    """Monthly Attendance & Homework Matrix — one table per group for every
    role (trainer, assistant, team lead, operations director, admin).

    Works on the academy's own Attendance / HomeworkResult rows (attendance
    and homework stay two separate records); this app only adds who may see
    and edit what, configurable thresholds and the audit log of changes."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.attendance_matrix"
    verbose_name = "Посещаемость и ДЗ (матрица)"
