import { useState } from 'react'
import { format, parseISO } from 'date-fns'
import { ru } from 'date-fns/locale'
import { CalendarClock, ClipboardCheck, MoveRight, XCircle } from 'lucide-react'
import { Link } from 'react-router-dom'

import { assistantApi } from '@/api/assistant'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { DatePicker } from '@/components/ui/DatePicker'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { useAssistantFormMutation } from '@/hooks/useAssistant'
import { useConflictCheck } from '@/hooks/useSchedule'
import { extractErrorMessage } from '@/lib/apiError'
import type { AssistantLesson } from '@/types/assistant'
import type { LessonConflict } from '@/types/schedule'
import { ConflictNotes } from '@/features/scheduleBoard/LessonPreviewModal'

import { Field, FormError, ModalActions } from '../ui'

/** One lesson: details, and the two operations on it — move (with the
 * trainer / group / room conflict check) and cancel. Opened from the
 * schedule, the dashboard and the global search. */
export function LessonModal({ lesson, onClose }: { lesson: AssistantLesson & { conflicts?: LessonConflict[] }; onClose: () => void }) {
  const [mode, setMode] = useState<'view' | 'move' | 'cancel'>('view')
  const [date, setDate] = useState(lesson.date)
  const [start, setStart] = useState(lesson.start)
  const [end, setEnd] = useState(lesson.end)
  const [reason, setReason] = useState('')
  const [reschedule, setReschedule] = useState(true)
  const move = useAssistantFormMutation(() => assistantApi.moveLesson(lesson.id, { date, start_time: start, end_time: end }), 'Занятие перенесено')
  const cancel = useAssistantFormMutation(() => assistantApi.cancelLesson(lesson.id, { reason, reschedule }), (res) =>
    res.rescheduled_to ? `Занятие отменено, тема перенесена на ${res.rescheduled_to.date} ${res.rescheduled_to.start}` : 'Занятие отменено')
  const editable = lesson.status === 'scheduled'
  const error = move.error ?? cancel.error
  const unchanged = date === lesson.date && start === lesson.start && end === lesson.end
  // Live preview of the backend's own check (trainer / group / room); the
  // move itself is still refused by the server on any clash.
  const check = useConflictCheck({ date, start, end, lesson: lesson.id }, mode === 'move' && !unchanged)
  const clashes = !unchanged && check.data && check.data.date === date && check.data.start === start && check.data.end === end ? check.data.conflicts : []

  return (
    <Modal isOpen onClose={onClose} title={`${lesson.group.name} · ${lesson.start}–${lesson.end}`} icon={<CalendarClock className="size-5 text-brand-600" aria-hidden />}>
      <dl className="mb-4 grid grid-cols-2 gap-3 rounded-lg bg-surface-muted p-3 text-sm">
        <div className="col-span-2"><dt className="field-label">Группа</dt><dd><Link to={`/assistant/groups/${lesson.group.id}`} onClick={onClose} className="font-medium text-brand-700 hover:underline">{lesson.group.name} — открыть группу</Link></dd></div>
        <div><dt className="field-label">Дата</dt><dd className="font-medium text-ink">{format(parseISO(lesson.date), 'd MMMM, EEEE', { locale: ru })}</dd></div>
        <div><dt className="field-label">Тренер</dt><dd className="font-medium text-ink">{lesson.teacher?.name ?? '—'}</dd></div>
        <div><dt className="field-label">Предмет</dt><dd className="font-medium text-ink">{lesson.subject?.name ?? '—'}</dd></div>
        <div><dt className="field-label">Кабинет</dt><dd className="font-medium text-ink">{lesson.room?.name ?? 'Не указан'}</dd></div>
        <div><dt className="field-label">Студентов</dt><dd className="font-medium text-ink">{lesson.students_count ?? 0}</dd></div>
        <div className="col-span-2"><dt className="field-label">Тема</dt><dd className="font-medium text-ink">№{lesson.lesson_number} {lesson.topic || '—'}</dd></div>
      </dl>
      {mode === 'view' ? <div className="mb-3"><ConflictNotes lesson={lesson} /></div> : null}
      {lesson.status !== 'scheduled' ? <Badge tone={lesson.status === 'cancelled' ? 'danger' : 'info'}>{lesson.status_display}</Badge> : null}

      {mode === 'move' ? (
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); move.mutate(undefined, { onSuccess: onClose }) }}>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Дата" htmlFor="move-date"><DatePicker id="move-date" value={date} onChange={(e) => setDate(e.target.value)} required /></Field>
            <Field label="Начало" htmlFor="move-start"><Input id="move-start" type="time" value={start} onChange={(e) => setStart(e.target.value)} required /></Field>
            <Field label="Окончание" htmlFor="move-end"><Input id="move-end" type="time" value={end} onChange={(e) => setEnd(e.target.value)} required /></Field>
          </div>
          {end && start && end <= start ? <p role="alert" className="text-sm text-danger">Время окончания должно быть позже времени начала.</p> : null}
          {clashes.length ? (
            <div role="alert" className="rounded-lg border border-danger/30 bg-danger-soft/60 px-3 py-2 text-sm">
              <p className="font-semibold text-danger">На это время есть пересечения:</p>
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-ink">{clashes.map((c, i) => <li key={i}>{c.message}</li>)}</ul>
            </div>
          ) : !unchanged && check.data?.ok && end > start ? (
            <p className="text-sm text-brand-700">Тренер, группа и кабинет свободны в это время.</p>
          ) : (
            <p className="text-xs text-ink-secondary">Тренер, группа и аудитория проверяются на занятость — конфликт сохранить нельзя.</p>
          )}
          <FormError message={error ? extractErrorMessage(error) : null} />
          <ModalActions>
            <Button type="button" variant="secondary" onClick={() => setMode('view')}>Назад</Button>
            <Button type="submit" disabled={move.isPending || !date || !start || !end || end <= start || unchanged || clashes.length > 0} isLoading={move.isPending}>Перенести</Button>
          </ModalActions>
        </form>
      ) : mode === 'cancel' ? (
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); cancel.mutate(undefined, { onSuccess: onClose }) }}>
          <Field label="Причина отмены" htmlFor="cancel-reason"><Input id="cancel-reason" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={255} /></Field>
          <label className="flex items-center gap-2 text-sm text-ink">
            <input type="checkbox" className="size-4 accent-brand-500" checked={reschedule} onChange={(e) => setReschedule(e.target.checked)} />
            Перенести тему на следующее свободное занятие
          </label>
          <FormError message={error ? extractErrorMessage(error) : null} />
          <ModalActions>
            <Button type="button" variant="secondary" onClick={() => setMode('view')}>Назад</Button>
            <Button type="submit" variant="danger" disabled={cancel.isPending} isLoading={cancel.isPending}>Отменить занятие</Button>
          </ModalActions>
        </form>
      ) : (
        <ModalActions>
          {lesson.status !== 'cancelled' ? (
            <Link to={`/assistant/attendance?date=${lesson.date}&group=${lesson.group.id}`} onClick={onClose}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-brand-200 px-4 text-sm font-medium text-brand-700 hover:bg-brand-50">
              <ClipboardCheck className="size-4" aria-hidden />Посещаемость
            </Link>
          ) : null}
          {editable ? <Button variant="danger" leftIcon={<XCircle className="size-4" aria-hidden />} onClick={() => setMode('cancel')}>Отменить</Button> : null}
          {editable ? <Button leftIcon={<MoveRight className="size-4" aria-hidden />} onClick={() => setMode('move')}>Перенести</Button> : null}
        </ModalActions>
      )}
    </Modal>
  )
}
