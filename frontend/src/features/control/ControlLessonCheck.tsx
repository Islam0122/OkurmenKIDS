import type { ReactNode } from 'react'
import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Badge } from '@/components/ui/Badge'
import type { ControlComponentState, ControlLesson } from '@/types/control'
import { formatDateShort, formatTimeRange } from '@/utils/format'

import { CONTROL_STATUS_TONE, LevelIcon } from './controlDisplay'
import { formatDateTime } from './format'

const HOMEWORK_CHECKED_LABEL: Partial<Record<ControlComponentState, string>> = {
  ok: 'Да',
  unchecked: 'Нет',
  waiting: 'Ещё рано — срок сдачи не наступил',
}

function StudentList({ title, students }: { title: string; students: { id: number; name: string }[] }) {
  if (students.length === 0) return null
  return (
    <div className="mt-2">
      <p className="text-xs font-medium text-ink-secondary">{title}</p>
      <ul className="mt-1 space-y-0.5 text-sm text-ink">
        {students.map((student) => (
          <li key={student.id}>• {student.name}</li>
        ))}
      </ul>
    </div>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <p className="text-xs text-ink-muted">{label}</p>
      <div className="text-sm text-ink">{children}</div>
    </div>
  )
}

/** One lesson's full check — who is responsible, what is filled, who is missing. */
export function ControlLessonCheck({ lesson }: { lesson: ControlLesson }) {
  const isDue = lesson.state === 'due'
  const attendanceLevel = lesson.attendance.state === 'ok' ? 'ok' : lesson.attendance.state === 'partial' ? 'warning' : 'danger'
  const gradesLevel = lesson.grades.state === 'ok' ? 'ok' : lesson.grades.state === 'partial' ? 'warning' : 'danger'

  return (
    <div className="space-y-4 rounded-lg border border-border bg-surface-muted p-4">
      <div className="grid grid-cols-2 gap-3">
        <Field label="Дата">
          {formatDateShort(lesson.date)} · {formatTimeRange(lesson.start_time, lesson.end_time)}
        </Field>
        <Field label="Занятие">№{lesson.lesson_number}{lesson.topic ? ` · ${lesson.topic}` : ''}</Field>
        <Field label="Ответственный тренер">
          {lesson.teacher?.name ?? 'Не назначен'}
          {lesson.planned_teacher ? (
            <span className="block text-xs text-ink-muted">замена, по программе — {lesson.planned_teacher.name}</span>
          ) : null}
        </Field>
        <Field label="Группа / предмет">
          {lesson.group.name}
          {lesson.subject ? ` · ${lesson.subject.name}` : ''}
        </Field>
      </div>

      {isDue ? (
        <>
          <section>
            <p className="flex items-center gap-2 text-sm font-semibold text-ink">
              {lesson.attendance.state === 'no_students' ? (
                <LevelIcon level="none" />
              ) : (
                <LevelIcon level={attendanceLevel} />
              )}
              Посещаемость
            </p>
            <p className="mt-1 text-sm text-ink-secondary">
              {lesson.attendance.state === 'no_students'
                ? 'В группе нет активных студентов'
                : `${lesson.attendance.marked} / ${lesson.attendance.total} студентов отмечено`}
            </p>
            <StudentList title="Не отмечены:" students={lesson.attendance.missing_students} />
          </section>

          <section>
            <p className="flex items-center gap-2 text-sm font-semibold text-ink">
              <LevelIcon
                level={
                  lesson.homework.state === 'ok'
                    ? 'ok'
                    : lesson.homework.state === 'missing' || lesson.homework.state === 'unchecked'
                      ? 'danger'
                      : 'none'
                }
              />
              Домашнее задание
            </p>
            {lesson.homework.not_required && !lesson.homework.given ? (
              <p className="mt-1 text-sm text-ink-secondary">Отмечено «ДЗ не требуется»</p>
            ) : (
              <dl className="mt-1 space-y-0.5 text-sm text-ink-secondary">
                <div>
                  Выдано: <span className="text-ink">{lesson.homework.given ? 'Да' : 'Нет'}</span>
                  {lesson.homework.deadline ? ` · срок ${formatDateShort(lesson.homework.deadline)}` : ''}
                </div>
                {lesson.homework.given ? (
                  <div>
                    Проверено: <span className="text-ink">{HOMEWORK_CHECKED_LABEL[lesson.homework.state] ?? '—'}</span>
                    {lesson.homework.pending_check > 0 ? ` (${lesson.homework.pending_check} ждут проверки)` : ''}
                  </div>
                ) : null}
              </dl>
            )}
          </section>

          <section>
            <p className="flex items-center gap-2 text-sm font-semibold text-ink">
              <LevelIcon level={lesson.grades.total > 0 ? gradesLevel : 'none'} />
              Баллы
            </p>
            <p className="mt-1 text-sm text-ink-secondary">
              {lesson.grades.total > 0
                ? `Выставлено: ${lesson.grades.given} / ${lesson.grades.total} · не выставлено: ${lesson.grades.missing}`
                : lesson.grades.state === 'waiting'
                  ? 'Срок сдачи ДЗ ещё не наступил'
                  : lesson.grades.state === 'no_homework'
                    ? 'Нет ДЗ — баллы выставить не за что'
                    : 'Не требуются'}
            </p>
            <StudentList title="Студенты без балла:" students={lesson.grades.missing_students} />
          </section>
        </>
      ) : null}

      <div className="grid grid-cols-2 gap-3 border-t border-border pt-3">
        <Field label="Статус занятия">{lesson.lesson_status_label}</Field>
        <Field label="Закрыл занятие">
          {lesson.closed_by ? `${lesson.closed_by.name}, ${formatDateTime(lesson.closed_at)}` : '—'}
        </Field>
        <Field label="Последнее изменение данных">{formatDateTime(lesson.last_activity_at)}</Field>
        <Field label="Контроль">
          <Badge tone={CONTROL_STATUS_TONE[lesson.status]}>{lesson.status_label}</Badge>
        </Field>
      </div>

      {lesson.notes.length > 0 ? (
        <ul className="space-y-0.5 text-xs text-ink-muted">
          {lesson.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}

      <Link
        to={`/app/lessons/${lesson.id}`}
        className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-brand-500 px-3 text-sm font-medium text-white hover:bg-brand-600"
      >
        Перейти к уроку <ArrowRight className="size-4" aria-hidden />
      </Link>
    </div>
  )
}
