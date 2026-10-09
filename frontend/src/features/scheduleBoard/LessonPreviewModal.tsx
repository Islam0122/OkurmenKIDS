import { format, parseISO } from 'date-fns'
import { ru } from 'date-fns/locale'
import { AlertTriangle, CalendarClock, ExternalLink } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Modal } from '@/components/ui/Modal'
import type { BoardLesson } from '@/types/schedule'

import { TrainerDot } from './LessonCard'
import { formatDuration } from './timeGrid'

/** A lesson's details for a reader (Team Lead): who, where, when, how long,
 * its status and its conflicts — and the way to the full lesson page. */
export function LessonPreviewModal({ lesson, detailsHref, onClose }: { lesson: BoardLesson; detailsHref?: string; onClose: () => void }) {
  return (
    <Modal isOpen onClose={onClose} title={`${lesson.group.name} · ${lesson.start}–${lesson.end}`} icon={<CalendarClock className="size-5 text-brand-600" aria-hidden />}>
      <LessonFacts lesson={lesson} />
      <ConflictNotes lesson={lesson} />
      {detailsHref ? (
        <div className="mt-4 flex justify-end">
          <Link to={detailsHref} onClick={onClose} className="inline-flex h-10 items-center gap-2 rounded-lg bg-brand-500 px-4 text-sm font-medium text-white hover:bg-brand-600">
            Открыть занятие <ExternalLink className="size-4" aria-hidden />
          </Link>
        </div>
      ) : null}
    </Modal>
  )
}

export function LessonFacts({ lesson }: { lesson: BoardLesson }) {
  return (
    <dl className="grid grid-cols-2 gap-3 rounded-lg bg-surface-muted p-3 text-sm">
      <div><dt className="field-label">Дата</dt><dd className="font-medium text-ink first-letter:uppercase">{format(parseISO(lesson.date), 'EEEE, d MMMM', { locale: ru })}</dd></div>
      <div><dt className="field-label">Время</dt><dd className="font-medium text-ink tabular-nums">{lesson.start}–{lesson.end} · {formatDuration(lesson.duration_minutes)}</dd></div>
      <div><dt className="field-label">Тренер</dt><dd className="flex items-center gap-1.5 font-medium text-ink"><TrainerDot color={lesson.teacher?.color} />{lesson.teacher?.name ?? '—'}</dd></div>
      <div><dt className="field-label">Кабинет</dt><dd className="font-medium text-ink">{lesson.room?.name ?? 'Не указан'}</dd></div>
      <div><dt className="field-label">Предмет</dt><dd className="font-medium text-ink">{lesson.subject?.name ?? '—'}</dd></div>
      <div><dt className="field-label">Статус</dt><dd className="font-medium text-ink">{lesson.status_display}{lesson.schedule_overridden ? ' · перенесено' : ''}</dd></div>
      <div><dt className="field-label">Студентов</dt><dd className="font-medium text-ink">{lesson.students_count ?? 0}</dd></div>
      <div><dt className="field-label">Тема</dt><dd className="font-medium text-ink">№{lesson.lesson_number} {lesson.topic || '—'}</dd></div>
    </dl>
  )
}

export function ConflictNotes({ lesson }: { lesson: { conflicts?: BoardLesson['conflicts'] } }) {
  if (!lesson.conflicts?.length) return null
  return (
    <div role="alert" className="mt-3 rounded-lg border border-danger/30 bg-danger-soft/60 px-3 py-2 text-sm">
      <p className="flex items-center gap-1.5 font-semibold text-danger"><AlertTriangle className="size-4" aria-hidden />Конфликт в расписании</p>
      <ul className="mt-1 list-disc space-y-0.5 pl-5 text-ink">
        {lesson.conflicts.map((conflict, index) => <li key={index}>{conflict.message}</li>)}
      </ul>
    </div>
  )
}
