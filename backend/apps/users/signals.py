from __future__ import annotations

import logging
from django.db.models.signals import post_migrate
from django.dispatch import receiver

logger = logging.getLogger(__name__)

DEFAULT_SUBJECTS = [
    {
        "name": "Backend",
        "description": "Серверная разработка и создание API.",
    },
    {
        "name": "Frontend",
        "description": "Разработка пользовательских интерфейсов и веб-приложений.",
    },
    {
        "name": "English",
        "description": "Изучение английского языка.",
    },
    {
        "name": "Soft Skills",
        "description": "Развитие коммуникации, командной работы и профессиональных навыков.",
    },
]


@receiver(post_migrate)
def create_default_subjects(sender, **kwargs) -> None:
    # Проверяем полное имя приложения (apps.users) или его label (users)
    if sender.name != "apps.users" and sender.label != "users":
        return

    # Получаем модель из app_config (sender) во избежание проблем с импортами во время миграций
    try:
        Subject = sender.get_model("Subject")
    except LookupError:
        return

    logger.info(
        "[signal:create_default_subjects] "
        "Initializing default subjects."
    )

    created_count = 0

    for subject_data in DEFAULT_SUBJECTS:
        subject, created = Subject.objects.get_or_create(
            name=subject_data["name"],
            defaults={
                "description": subject_data["description"],
                "is_active": True,
            },
        )

        if created:
            created_count += 1
            logger.info(
                "[signal:create_default_subjects] "
                "Subject created. id=%s name=%s",
                subject.id,
                subject.name,
            )

    logger.info(
        "[signal:create_default_subjects] "
        "Initialization completed. created=%s",
        created_count,
    )