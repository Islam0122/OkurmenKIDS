import { useMemo, useState } from 'react'
import {
  addDays, addMonths, eachDayOfInterval, endOfMonth, endOfWeek, format, isSameMonth, isToday, parseISO, startOfMonth, startOfWeek,
} from 'date-fns'
import { ru } from 'date-fns/locale'
import { AlertTriangle, CalendarClock, CalendarPlus, ChevronLeft, ChevronRight, MoveRight, XCircle } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'

import { assistantApi } from '@/api/assistant'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { DatePicker } from '@/components/ui/DatePicker'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { useAssistantFormMutation, useAssistantOptions, useAssistantSchedule } from '@/hooks/useAssistant'
import { extractErrorMessage } from '@/lib/apiError'
import type { AssistantLesson, ScheduleConflict } from '@/types/assistant'
import { cn } from '@/utils/cn'

import { useAssistantActions } from '../actions/AssistantActions'
import { Field, FormError, ModalActions } from '../ui'

type View = 'day' | 'week' | 'month'
const VIEWS: { value: View; label: string }[] = [
  { value: 'day', label: 'День' },
  { value: 'week', label: 'Неделя' },
  { value: 'month', label: 'Месяц' },
]
const iso = (date: Date) => format(date, 'yyyy-MM-dd')

function range(view: View, anchor: Date): { start: Date; end: Date } {
  if (view === 'day') return { start: anchor, end: anchor }
  if (view === 'week') return { start: startOfWeek(anchor, { weekStartsOn: 1 }), end: endOfWeek(anchor, { weekStartsOn: 1 }) }
  return { start: startOfWeek(startOfMonth(anchor), { weekStartsOn: 1 }), end: endOfWeek(endOfMonth(anchor), { weekStartsOn: 1 }) }
}

function LessonChip({ lesson, onOpen }: { lesson: AssistantLesson; onOpen: (lesson: AssistantLesson) => void }) {
  return (
    <button
      type="button"
      onClick={() => onOpen(lesson)}
      className={cn(
        'w-full min-w-0 rounded-lg border px-2.5 py-2 text-left transition-colors hover:border-brand-200 hover:bg-brand-50/50',
        lesson.status === 'cancelled' ? 'border-danger/20 bg-danger-soft/40 line-through' : 'border-border bg-surface',
      )}
    >
      <p className="whitespace-nowrap text-xs font-semibold text-brand-700">{lesson.start}–{lesson.end}</p>
      <p className="truncate text-sm font-medium text-ink">{lesson.group.name}</p>
      <p className="truncate text-xs text-ink-secondary">{lesson.teacher?.name ?? '—'}</p>
      <p className="truncate text-xs text-ink-muted">{lesson.subject?.name ?? '—'} · {lesson.students_count ?? 0} студ.{lesson.room ? ` · ${lesson.room.name}` : ''}</p>
    </button>
  )
}

function LessonModal({ lesson, onClose }: { lesson: AssistantLesson; onClose: () => void }) {
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
          <Link to={`/assistant/groups/${lesson.group.id}`} className="inline-flex h-10 items-center justify-center rounded-lg px-4 text-sm font-medium text-brand-700 hover:bg-brand-50 sm:mr-auto">Открыть группу</Link>
          {editable ? <Button variant="danger" leftIcon={<XCircle className="size-4" aria-hidden />} onClick={() => setMode('cancel')}>Отменить</Button> : null}
          {editable ? <Button leftIcon={<MoveRight className="size-4" aria-hidden />} onClick={() => setMode('move')}>Перенести</Button> : null}
        </ModalActions>
      )}
    </Modal>
  )
}

function ConflictsCard({ conflicts }: { conflicts: ScheduleConflict[] }) {
  return (
    <Card title="Конфликты в расписании" description="Слоты, где один тренер, аудитория или группа заняты дважды в одно время." className="mb-6 border-danger/30">
      <ul className="space-y-3">
        {conflicts.map((conflict, index) => (
          <li key={index} className="rounded-lg bg-danger-soft/60 px-3 py-2 text-sm">
            <p className="font-medium text-danger"><AlertTriangle className="mr-1.5 inline size-4" aria-hidden />{conflict.kind_label} «{conflict.name}» · {conflict.day_label}</p>
            <ul className="mt-1 text-ink">
              {conflict.slots.map((slot, i) => (
                <li key={i}><Link to={`/assistant/groups/${slot.group.id}?tab=schedule`} className="hover:text-brand-700">{slot.group.name}</Link> — {slot.start}–{slot.end} ({slot.teacher.name})</li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </Card>
  )
}

export function AssistantSchedulePage() {
  const [params, setParams] = useSearchParams()
  const view = (VIEWS.some((v) => v.value === params.get('view')) ? params.get('view') : 'week') as View
  const [anchor, setAnchor] = useState(() => (params.get('date') ? parseISO(params.get('date') as string) : new Date()))
  const [group, setGroup] = useState('')
  const [teacher, setTeacher] = useState('')
  const [openLesson, setOpenLesson] = useState<AssistantLesson | null>(null)
  const [showConflicts, setShowConflicts] = useState(params.get('conflicts') === '1')
  const { open } = useAssistantActions()
  const { data: options } = useAssistantOptions()
  const { start, end } = range(view, anchor)
  const { data, isPending, isError, refetch } = useAssistantSchedule({
    start: iso(start), end: iso(end), group: group ? Number(group) : undefined, teacher: teacher ? Number(teacher) : undefined,
  })

  const byDay = useMemo(() => {
    const map = new Map<string, AssistantLesson[]>()
    for (const lesson of data?.lessons ?? []) map.set(lesson.date, [...(map.get(lesson.date) ?? []), lesson])
    return map
  }, [data])

  const shift = (direction: 1 | -1) =>
    setAnchor((current) => (view === 'day' ? addDays(current, direction) : view === 'week' ? addDays(current, 7 * direction) : addMonths(current, direction)))
  const setView = (value: View) => {
    const next = new URLSearchParams(params)
    next.set('view', value)
    setParams(next, { replace: true })
  }
  const title = view === 'day'
    ? format(anchor, 'd MMMM yyyy, EEEE', { locale: ru })
    : view === 'week' ? `${format(start, 'd MMM', { locale: ru })} – ${format(end, 'd MMM yyyy', { locale: ru })}` : format(anchor, 'LLLL yyyy', { locale: ru })
  const conflicts = data?.conflicts ?? []
  const days = eachDayOfInterval({ start, end })

  return (
    <div>
      <PageHeader
        title="Расписание"
        description="Занятия всех групп. Нажмите на занятие, чтобы перенести или отменить его."
        actions={<Button leftIcon={<CalendarPlus className="size-4" aria-hidden />} onClick={() => open({ type: 'schedule' })}>Расписание</Button>}
      />
      <FilterBar>
        <SegmentedControl aria-label="Вид" options={VIEWS} value={view} onChange={setView} />
        <div className="flex items-center gap-1">
          <Button variant="secondary" size="md" aria-label="Назад" onClick={() => shift(-1)}><ChevronLeft className="size-4" aria-hidden /></Button>
          <Button variant="secondary" onClick={() => setAnchor(new Date())}>Сегодня</Button>
          <Button variant="secondary" size="md" aria-label="Вперёд" onClick={() => shift(1)}><ChevronRight className="size-4" aria-hidden /></Button>
        </div>
        <FilterField>
          <Select aria-label="Группа" value={group} placeholder="Все группы" onChange={(e) => setGroup(e.target.value)} options={(options?.groups ?? []).map((g) => ({ value: String(g.id), label: g.name }))} />
        </FilterField>
        <FilterField>
          <Select aria-label="Тренер" value={teacher} placeholder="Все тренеры" onChange={(e) => setTeacher(e.target.value)} options={(options?.teachers ?? []).map((t) => ({ value: String(t.id), label: t.name }))} />
        </FilterField>
        {conflicts.length ? (
          <button type="button" onClick={() => setShowConflicts((v) => !v)} className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-danger/30 bg-danger-soft px-3 text-sm font-medium text-danger">
            <AlertTriangle className="size-4" aria-hidden /> Конфликты: {conflicts.length}
          </button>
        ) : null}
      </FilterBar>

      {showConflicts && conflicts.length ? <ConflictsCard conflicts={conflicts} /> : null}
      <h2 className="section-title mb-3 first-letter:uppercase">{title}</h2>
      {isPending ? <LoadingState label="Загружаем расписание…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}

      {data && view === 'day' ? (
        (byDay.get(iso(anchor)) ?? []).length === 0 ? (
          <EmptyState icon={CalendarClock} title="В этот день занятий нет" action={<Button variant="secondary" leftIcon={<CalendarPlus className="size-4" aria-hidden />} onClick={() => open({ type: 'schedule' })}>Добавить расписание</Button>} />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {(byDay.get(iso(anchor)) ?? []).map((lesson) => <LessonChip key={lesson.id} lesson={lesson} onOpen={setOpenLesson} />)}
          </div>
        )
      ) : null}

      {data && view === 'week' ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
          {days.map((day) => {
            const lessons = byDay.get(iso(day)) ?? []
            return (
              <div key={iso(day)} className={cn('min-w-0 rounded-xl border bg-surface p-2', isToday(day) ? 'border-brand-200' : 'border-border')}>
                <button type="button" onClick={() => { setAnchor(day); setView('day') }} className="mb-2 w-full px-1 text-left">
                  <span className={cn('text-xs font-semibold uppercase', isToday(day) ? 'text-brand-700' : 'text-ink-secondary')}>{format(day, 'EEEEEE', { locale: ru })}</span>
                  <span className="ml-1.5 text-sm font-semibold text-ink">{format(day, 'd')}</span>
                </button>
                <div className="space-y-1.5">
                  {lessons.length === 0 ? <p className="px-1 text-xs text-ink-muted">—</p> : lessons.map((lesson) => <LessonChip key={lesson.id} lesson={lesson} onOpen={setOpenLesson} />)}
                </div>
              </div>
            )
          })}
        </div>
      ) : null}

      {data && view === 'month' ? (
        <div className="card overflow-hidden">
          <div className="grid grid-cols-7 border-b border-border bg-surface-muted text-center text-xs font-semibold text-ink-secondary">
            {['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'].map((d) => <div key={d} className="py-2">{d}</div>)}
          </div>
          <div className="grid grid-cols-7">
            {days.map((day) => {
              const lessons = byDay.get(iso(day)) ?? []
              return (
                <button key={iso(day)} type="button" onClick={() => { setAnchor(day); setView('day') }}
                  className={cn('flex min-h-20 min-w-0 flex-col items-start justify-start border-r border-b border-border p-1.5 text-left hover:bg-surface-hover sm:min-h-24', !isSameMonth(day, anchor) && 'bg-surface-muted/60 text-ink-muted')}>
                  <span className={cn('inline-flex size-6 items-center justify-center rounded-full text-xs font-semibold', isToday(day) ? 'bg-brand-500 text-white' : 'text-ink')}>{format(day, 'd')}</span>
                  {lessons.length ? (
                    <>
                      <ul className="mt-1 hidden w-full space-y-0.5 lg:block">
                        {lessons.slice(0, 3).map((l) => <li key={l.id} className="truncate text-2xs text-ink-secondary">{l.start} {l.group.name}</li>)}
                        {lessons.length > 3 ? <li className="text-2xs font-medium text-brand-700">ещё {lessons.length - 3}</li> : null}
                      </ul>
                      <span className="mt-1 block text-2xs font-medium text-brand-700 lg:hidden">{lessons.length} зан.</span>
                    </>
                  ) : null}
                </button>
              )
            })}
          </div>
        </div>
      ) : null}

      {openLesson ? <LessonModal lesson={openLesson} onClose={() => setOpenLesson(null)} /> : null}
    </div>
  )
}
