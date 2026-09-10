from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.templatetags.static import static
from django.template.loader import render_to_string
from apps.users.models import Subject, Teacher, User

logger = logging.getLogger(__name__)


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
            is_verified=True,
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
    subject = "OkurmenKIDS — доступ к системе"

    logo_url = static('images/img.png')

    context = {
        "user": user,
        "password": password,
        "login_url": f"{settings.SITE_URL}/login/",
        "logo_url":"https://encrypted-tbn0.gstatic.com/images",
    }

    html_message = render_to_string(
        "emails/teacher_credentials.html",
        context,
    )

    text_message = (
        f"Здравствуйте, {user.first_name}!\n\n"
        "Ваш аккаунт тренера в системе OkurmenKIDS был создан.\n\n"
        f"Логин: {user.username}\n"
        f"Пароль: {password}\n\n"
        f"Вход: {settings.SITE_URL}/login/"
    )

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )

    email.attach_alternative(html_message, "text/html")
    email.send(fail_silently=False)