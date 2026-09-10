"""Business logic for the users app.

Views and the Django admin should stay thin and delegate to these functions
rather than embedding business rules directly.

Note: Trainer accounts never get a backend-generated password. Admin always
supplies the password (at creation, and whenever it needs to change), and
that same password is what gets emailed to the trainer.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction

from apps.users.models import Subject, Teacher, User

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Teacher creation
# ---------------------------------------------------------------------------

@dataclass
class TeacherCreationResult:
    teacher: Teacher
    email_sent: bool
    email_error: str | None = None


def create_teacher(
    *,
    username: str,
    email: str,
    first_name: str,
    password: str,
    last_name: str = "",
    phone: str = "",
    image=None,
    subjects: list[Subject] | None = None,
    position: str = "Тренер",
    experience_years: int = 0,
    bio: str = "",
    hire_date=None,
    is_active: bool = True,
    send_email: bool = True,
) -> TeacherCreationResult:
    with transaction.atomic():
        user = User(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            role=User.Role.TEACHER,
            is_verified=False,
        )
        user.is_active = is_active
        user.set_password(password)
        user.full_clean(exclude=["password"])
        user.save()

        teacher = Teacher(
            user=user,
            phone=phone,
            image=image,
            position=position,
            experience_years=experience_years,
            bio=bio,
            hire_date=hire_date,
            is_active=is_active,
        )
        teacher.full_clean()
        teacher.save()

        if subjects:
            teacher.subjects.set(subjects)

    email_sent = False
    email_error = None
    if send_email:
        email_sent, email_error = _try_send_credentials(user, password)

    return TeacherCreationResult(
        teacher=teacher,
        email_sent=email_sent,
        email_error=email_error,
    )


def change_teacher_password_and_send(teacher: Teacher, new_password: str) -> TeacherCreationResult:
    """Set a new Admin-supplied password for an existing teacher and email it.

    The previous password becomes invalid immediately. There is no way to
    resend a teacher's *existing* password — Django only stores a hash — so
    this is the only supported way to get a trainer working credentials
    again (used by the "Изменить пароль и отправить" admin action).
    """
    user = teacher.user
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])

    email_sent, email_error = _try_send_credentials(user, new_password)

    return TeacherCreationResult(
        teacher=teacher,
        email_sent=email_sent,
        email_error=email_error,
    )


def _try_send_credentials(user: User, password: str) -> tuple[bool, str | None]:
    try:
        send_teacher_credentials(user, password)
        return True, None
    except Exception as exc:  # noqa: BLE001 - we want to swallow & report, not crash account creation
        logger.exception("Failed to send credentials email to user id=%s", user.pk)
        return False, str(exc)


def send_teacher_credentials(user: User, password: str) -> None:
    """Send the trainer their login credentials by email.

    Credentials are never logged — only success/failure is logged by the
    caller, and never with the password value.
    """
    subject = "OkurmenKIDS — доступ к системе"
    message = (
        "OkurmenKIDS\n\n"
        f"Здравствуйте, {user.first_name}!\n\n"
        "Ваш аккаунт тренера в системе OkurmenKIDS был создан.\n\n"
        "Логин:\n"
        f"{user.username}\n\n"
        "Пароль:\n"
        f"{password}\n\n"
        "Для входа используйте систему OkurmenKIDS.\n\n"
        "С уважением,\n"
        "OkurmenKIDS Academy"
    )
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
