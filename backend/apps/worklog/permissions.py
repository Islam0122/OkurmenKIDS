"""Who uses the work log: the Team Lead writes their own journal, tasks and
reports; Admin (management) reads all of it to see the Team Lead's real
work and can write too. Only the author edits or deletes a record.
Trainers and everyone else: no access."""
from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.users.permissions import is_admin_user, is_team_lead


class WorkLogAccess(BasePermission):
    message = "Рабочий журнал доступен руководителю тренеров и администрации."

    def has_permission(self, request, view) -> bool:
        return is_team_lead(request.user) or is_admin_user(request.user)

    def has_object_permission(self, request, view, obj) -> bool:
        if request.method in SAFE_METHODS:
            return True
        self.message = "Изменять запись может только её автор."
        return obj.author_id == request.user.pk
