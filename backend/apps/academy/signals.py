"""Signal wiring for the academy app — deliberately *without* automatic
lesson generation.

Lesson generation used to run on every Group/GroupSchedule save and
GroupSchedule delete. That was the root cause of lessons dated years past a
group's real period: the Workspace's "Добавить учебную программу" form (and
any API client adding slots one request at a time) saves a program's
Monday/Wednesday/Friday slots one by one, so the very first save — Monday
alone — already fired a full generation, and the shared course plan's
lesson_number cursor spread all 144 plan rows over 144 consecutive Mondays
(09.09.2026 → 11.06.2029). The Wednesday/Friday slots saved a moment later
then found every lesson_number already taken and generated nothing. The
same greediness also let one teacher's first slot swallow lessons meant for
another teacher's not-yet-added program.

Generation walks the *whole* schedule at once, so it only produces the
right calendar once that schedule is complete — which only the admin
knows. It is therefore an explicit, idempotent action: the Workspace's
"Сгенерировать занятия" button, the Group admin action, or
`POST /api/v1/groups/{id}/generate-lessons/` — all backed by
services.lesson_generator, safe to click as often as needed.

`_defer_schedule_sync` (still set by a few callers, e.g.
services.group_schedule_sync and generate_mock_data) is now a harmless
no-op kept for backward compatibility.
"""
