from django.apps import AppConfig


class StaffAttendanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.staff_attendance"
    label = "staff_attendance"
    verbose_name = "Учёт прихода и ухода сотрудников"
