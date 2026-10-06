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
import { extractErrorMessage } from '@/lib/apiError'
import type { AssistantLesson } from '@/types/assistant'

import { Field, FormError, ModalActions } from '../ui'

/** One lesson: details, and the two operations on it — move (with the
 * trainer / group / room conflict check) and cancel. Opened from the
 * schedule, the dashboard and the global search. */
export function LessonModal({ lesson, onClose }: { lesson: AssistantLesson; onClose: () => void }) {
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

  return (
    <Modal isOpen onClose={onClose} title={`${lesson.group.name} · ${lesson.start}–${lesson.end}`} icon={<CalendarClock className="size-5 text-brand-600" aria-hidden />}>
      <dl className="mb-4 grid grid-cols-2 gap-3 rounded-lg bg-surface-muted p-3 text-sm">
        <div><dt className="field-label">Дата</dt><dd className="font-medium text-ink">{format(parseISO(lesson.date), 'd MMMM, EEEE', { locale: ru })}</dd></div>
        <div><dt className="field-label">Тренер</dt><dd className="font-medium text-ink">{lesson.teacher?.name ?? '—'}</dd></div>
        <div><dt className="field-label">Предмет</dt><dd className="font-medium text-ink">{lesson.subject?.name ?? '—'}</dd></div>
        <div><dt className="field-label">Студентов</dt><dd className="font-medium text-ink">{lesson.students_count ?? 0}</dd></div>
        <div className="col-span-2"><dt className="field-label">Тема</dt><dd className="font-medium text-ink">№{lesson.lesson_number} {lesson.topic || '—'}</dd></div>
      </dl>
      {lesson.status !== 'scheduled' ? <Badge tone={lesson.status === 'cancelled' ? 'danger' : 'info'}>{lesson.status_display}</Badge> : null}

      {mode === 'move' ? (
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); move.mutate(undefined, { onSuccess: onClose }) }}>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Дата" htmlFor="move-date"><DatePicker id="move-date" value={date} onChange={(e) => setDate(e.target.value)} required /></Field>
            <Field label="Начало" htmlFor="move-start"><Input id="move-start" type="time" value={start} onChange={(e) => setStart(e.target.value)} required /></Field>
            <Field label="Окончание" htmlFor="move-end"><Input id="move-end" type="time" value={end} onChange={(e) => setEnd(e.target.value)} required /></Field>
          </div>
          <p className="text-xs text-ink-secondary">Тренер, группа и аудитория проверяются на занятость — конфликт сохранить нельзя.</p>
          <FormError message={error ? extractErrorMessage(error) : null} />
          <ModalActions>
            <Button type="button" variant="secondary" onClick={() => setMode('view')}>Назад</Button>
            <Button type="submit" disabled={move.isPending || !date || !start || !end || end <= start} isLoading={move.isPending}>Перенести</Button>
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
          <Link to={`/assistant/groups/${lesson.group.id}`} onClick={onClose} className="inline-flex h-10 items-center justify-center rounded-lg px-4 text-sm font-medium text-brand-700 hover:bg-brand-50 sm:mr-auto">Открыть группу</Link>
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
