"""Заполняет демо-базу кабинета маркетинга обезличенными данными.

Запускать только с настройками video_settings (отдельная SQLite-база):

    PYTHONPATH=backend:marketing_video/demo DJANGO_SETTINGS_MODULE=video_settings \
        python marketing_video/demo/seed_demo.py

Все люди вымышленные, контактов нет. Даты считаются от сегодняшнего дня,
поэтому сводка и отчёты выглядят «живыми» в любой день записи.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, time, timedelta

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "video_settings")
django.setup()

from django.conf import settings  # noqa: E402
from django.utils import timezone  # noqa: E402

from apps.marketing.models import ContentItem, MarketingTask  # noqa: E402
from apps.users.models import User  # noqa: E402

DB_NAME = str(settings.DATABASES["default"]["NAME"])
if "demo" not in DB_NAME:
    sys.exit(f"Отказ: база {DB_NAME!r} не похожа на демо-базу. Сид запускается только на video_settings.")

PASSWORD = os.environ.get("MARKETING_DEMO_PASSWORD", "demo-video-2026")
TEAM = [
    ("demo_marketing", "Алина", "Демидова"),
    ("demo_smm", "Тимур", "Садыков"),
    ("demo_design", "Мира", "Ким"),
]

today = timezone.localdate()
tz = timezone.get_current_timezone()


def at(day, hour=10, minute=0):
    return timezone.make_aware(datetime.combine(day, time(hour, minute)), tz)


def main():
    ContentItem.objects.all().delete()
    MarketingTask.objects.all().delete()
    users = []
    for username, first, last in TEAM:
        user, _ = User.objects.update_or_create(
            username=username,
            defaults={"email": f"{username}@example.com", "first_name": first, "last_name": last,
                      "role": User.Role.MARKETING, "is_active": True, "is_verified": True},
        )
        user.set_password(PASSWORD)
        user.save()
        users.append(user)
    alina, timur, mira = users

    D = lambda offset: today + timedelta(days=offset)  # noqa: E731
    S = ContentItem.Status
    content = [
        # (смещение, время, тема, канал, формат, статус, ответственный)
        (-27, "11:00", "Как выбрать первый IT-курс для ребёнка 7–9 лет", "website", "article", S.PUBLISHED, alina),
        (-24, "19:00", "Неделя Scratch: игра, которую ученики сделали за урок", "instagram", "carousel", S.PUBLISHED, mira),
        (-21, "18:30", "Один день в группе Python: закулисье занятия", "tiktok", "reels", S.PUBLISHED, timur),
        (-19, "12:00", "Анонс открытого урока по робототехнике", "telegram", "post", S.PUBLISHED, alina),
        (-17, "19:00", "Отзыв выпускника курса веб-разработки", "instagram", "reels", S.PUBLISHED, timur),
        (-14, "18:00", "Итоги внутреннего хакатона", "youtube", "video", S.PUBLISHED, mira),
        (-12, "19:00", "Советы родителям: сколько времени ребёнку за компьютером", "instagram", "post", S.SCHEDULED, alina),
        (-10, "12:00", "Подборка проектов учеников месяца", "telegram", "post", S.PUBLISHED, alina),
        (-7, "18:30", "Лайфхак по Python за 30 секунд", "tiktok", "reels", S.PUBLISHED, timur),
        (-5, "19:00", "Знакомство с тренерами: кто ведёт занятия", "instagram", "carousel", S.REVIEW, mira),
        (-3, "11:00", "Расписание открытых уроков на следующую неделю", "facebook", "post", S.PUBLISHED, alina),
        (-1, "19:00", "Сторис с открытого урока по робототехнике", "instagram", "stories", S.PUBLISHED, timur),
        (0, "18:00", "Объявление о старте новых групп", "telegram", "post", S.SCHEDULED, alina),
        (1, "19:00", "Ответы на частые вопросы родителей", "instagram", "carousel", S.SCHEDULED, mira),
        (2, "18:30", "Мини-челлендж: собери игру за 10 минут", "tiktok", "reels", S.REVIEW, timur),
        (4, "12:00", "Истории успеха: проект ученицы на конкурсе", "website", "article", S.PREPARING, alina),
        (6, "19:00", "Экскурсия по учебному центру", "youtube", "video", S.SCHEDULED, mira),
        (8, "18:00", "Напоминание об открытом уроке", "whatsapp", "post", S.PREPARING, alina),
        (11, "19:00", "Разбор домашнего задания по Scratch", "instagram", "reels", S.PREPARING, timur),
        # Прошлый месяц — чтобы было что листать в сводке и отчётах.
        (-40, "19:00", "Старт учебного года: приветственное видео", "youtube", "video", S.PUBLISHED, mira),
        (-36, "12:00", "Как проходит пробное занятие", "telegram", "post", S.PUBLISHED, alina),
        (-33, "18:30", "Ученики рассказывают о любимом курсе", "tiktok", "reels", S.PUBLISHED, timur),
        (-31, "19:00", "Фотоотчёт с родительского собрания", "instagram", "carousel", S.SCHEDULED, mira),
    ]
    ideas = [
        ("Серия «IT-профессии простыми словами»", "youtube", "video", mira),
        ("Подкаст с тренерами о мотивации детей", "website", "article", None),
        ("Конкурс рисунков роботов среди учеников", "instagram", "post", timur),
        ("Гайд для родителей по безопасности в интернете", "telegram", "article", alina),
    ]
    for offset, hm, title, channel, fmt, status, who in content:
        day = D(offset)
        hour, minute = map(int, hm.split(":"))
        item = ContentItem.objects.create(
            title=title, channel=channel, format=fmt, status=status, responsible=who, created_by=alina,
            publish_date=day, publish_time=time(hour, minute),
            description="Демо-запись для обучающего видео.",
            post_url="https://example.com/post" if status == S.PUBLISHED else "",
            published_at=at(day, hour, minute) if status == S.PUBLISHED else None,
        )
        ContentItem.objects.filter(pk=item.pk).update(created_at=at(day - timedelta(days=10)))
    for title, channel, fmt, who in ideas:
        ContentItem.objects.create(title=title, channel=channel, format=fmt, status=S.IDEA, responsible=who,
                                   created_by=alina, description="Идея для обсуждения на планёрке.")

    T, P = MarketingTask.Status, MarketingTask.Priority
    tasks = [
        # (название, срок, приоритет, статус, ответственный, создана, выполнена)
        ("Снять видео с открытого урока по робототехнике", -2, P.HIGH, T.DONE, timur, -9, -3),
        ("Подготовить карусель «Знакомство с тренерами»", -6, P.MEDIUM, T.DONE, mira, -15, -8),
        ("Обновить шапку профиля в Instagram", -20, P.LOW, T.DONE, mira, -25, -21),
        ("Собрать отзывы родителей за месяц", -11, P.MEDIUM, T.DONE, alina, -18, -12),
        ("Согласовать расписание открытых уроков с ассистентом", -5, P.HIGH, T.DONE, alina, -12, -6),
        ("Сверстать статью для сайта о выборе курса", -26, P.MEDIUM, T.DONE, alina, -30, -24),
        ("Смонтировать ролик об итогах хакатона", -16, P.HIGH, T.DONE, mira, -22, -14),
        ("Написать тексты для сторис на неделю", -2, P.MEDIUM, T.IN_PROGRESS, timur, -7, None),
        ("Подготовить фото для поста о новых группах", 0, P.HIGH, T.IN_PROGRESS, mira, -4, None),
        ("Договориться о съёмке экскурсии по центру", 3, P.MEDIUM, T.IN_PROGRESS, alina, -3, None),
        ("Ответить на комментарии под постом о хакатоне", -4, P.LOW, T.TODO, timur, -8, None),
        ("Подготовить сценарий челленджа для TikTok", 1, P.HIGH, T.TODO, timur, -2, None),
        ("Составить контент-план на следующий месяц", 5, P.HIGH, T.TODO, alina, -1, None),
        ("Собрать идеи для рубрики «IT-профессии»", None, P.LOW, T.TODO, mira, -1, None),
    ]
    for title, due, priority, status, who, created, done in tasks:
        task = MarketingTask.objects.create(
            title=title, due_date=D(due) if due is not None else None, priority=priority, status=status,
            responsible=who, created_by=alina, description="Демо-задача для обучающего видео.",
            completed_at=at(D(done), 17) if done is not None else None,
        )
        MarketingTask.objects.filter(pk=task.pk).update(created_at=at(D(created), 9))

    print(f"Демо-данные готовы на {today}: {ContentItem.objects.count()} публикаций, "
          f"{MarketingTask.objects.count()} задач, команда — {len(users)} человека. База: {DB_NAME}")


if __name__ == "__main__":
    main()
