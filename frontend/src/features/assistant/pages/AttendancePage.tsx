import { useEffect, useState } from 'react'
import { addDays, format, parseISO } from 'date-fns'
import { ru } from 'date-fns/locale'
import { Check, ChevronDown, ChevronLeft, ChevronRight, ClipboardCheck, Clock, ShieldCheck, X } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'

import { assistantApi } from '@/api/assistant'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { DatePicker } from '@/components/ui/DatePicker'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { LoadingState } from '@/components/ui/LoadingState'
import { Select } from '@/components/ui/Select'
import { useAssistantAttendance, useAssistantMutation, useAssistantOptions } from '@/hooks/useAssistant'
import type { AttendanceLesson, AttendanceStatus } from '@/types/assistant'
import { cn } from '@/utils/cn'

import { todayIso } from '../ui'

const MARKS: { value: AttendanceStatus; label: string; icon: LucideIcon; active: string }[] = [
  { value: 'present', label: 'Был', icon: Check, active: 'border-brand-500 bg-brand-500 text-white' },
  { value: 'late', label: 'Опоздал', icon: Clock, active: 'border-warning bg-warning text-white' },
  { value: 'absent', label: 'Не был', icon: X, active: 'border-danger bg-danger text-white' },
  { value: 'excused', label: 'Уважительная', icon: ShieldCheck, active: 'border-info bg-info text-white' },
]

/** The roster of one lesson: mark or correct, save only what changed. */
function Roster({ lesson }: { lesson: AttendanceLesson }) {
  const [marks, setMarks] = useState<Record<number, AttendanceStatus | null>>({})
  useEffect(() => {
    setMarks(Object.fromEntries(lesson.records.map((r) => [r.student.id, r.status])))
  }, [lesson])
  const changed = lesson.records.filter((r) => marks[r.student.id] && marks[r.student.id] !== r.status)
  const save = useAssistantMutation(
    () => assistantApi.markAttendance(lesson.id, changed.map((r) => ({ student: r.student.id, status: marks[r.student.id] as AttendanceStatus }))),
    `${lesson.group.name}: посещаемость сохранена`,
  )
  const allPresent = () => setMarks(Object.fromEntries(lesson.records.map((r) => [r.student.id, marks[r.student.id] ?? 'present'])))

  if (lesson.records.length === 0) return <p className="px-4 pb-3 text-sm text-ink-secondary">В группе нет активных студентов.</p>
  return (
    <div className="border-t border-border bg-surface-muted/40">
      <ul className="divide-y divide-border">
        {lesson.records.map((record) => (
          <li key={record.student.id} className="flex items-center justify-between gap-3 px-4 py-1.5">
            <span className="min-w-0 truncate text-sm text-ink">{record.student.name}</span>
            <div className="flex shrink-0 gap-1" role="radiogroup" aria-label={`Отметка: ${record.student.name}`}>
              {MARKS.map((mark) => {
                const active = marks[record.student.id] === mark.value
                return (
                  <button key={mark.value} type="button" role="radio" aria-checked={active} title={mark.label} aria-label={mark.label}
                    onClick={() => setMarks((m) => ({ ...m, [record.student.id]: mark.value }))}
                    className={cn('flex size-8 items-center justify-center rounded-md border transition-colors', active ? mark.active : 'border-border bg-surface text-ink-muted hover:bg-surface-hover')}>
                    <mark.icon className="size-4" aria-hidden />
                  </button>
                )
              })}
            </div>
          </li>
        ))}
      </ul>
      <div className="flex flex-col-reverse gap-2 border-t border-border px-4 py-2.5 sm:flex-row sm:justify-end">
        <Button size="sm" variant="secondary" onClick={allPresent}>Остальные — «был»</Button>
        <Button size="sm" disabled={changed.length === 0 || save.isPending} isLoading={save.isPending} onClick={() => save.mutate(undefined)}>
          Сохранить{changed.length ? ` (${changed.length})` : ''}
        </Button>
      </div>
    </div>
  )
}

function LessonRow({ lesson, expanded, onToggle, showDate }: { lesson: AttendanceLesson; expanded: boolean; onToggle: () => void; showDate: boolean }) {
  const done = lesson.unmarked === 0 && lesson.records.length > 0
  return (
    <li className="card overflow-hidden">
      <button type="button" onClick={onToggle} aria-expanded={expanded}
        className="flex w-full flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2.5 text-left hover:bg-surface-hover">
        <span className="w-24 text-sm font-semibold text-ink tabular-nums">
          {showDate ? <span className="block text-2xs font-normal text-ink-muted">{format(parseISO(lesson.date), 'd MMM, EEEEEE', { locale: ru })}</span> : null}
          {lesson.start}–{lesson.end}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate font-semibold text-ink">{lesson.group.name}</span>
          <span className="block truncate text-xs text-ink-secondary">{lesson.subject?.name ?? '—'} · {lesson.teacher?.name ?? '—'} · {lesson.records.length} студ.</span>
        </span>
        <span className="flex items-center gap-3 text-sm tabular-nums">
          <span className="text-brand-700">Были {lesson.present}</span>
          <span className="text-danger">Нет {lesson.absent}</span>
          {lesson.unmarked ? <span className="rounded-full bg-warning-soft px-2 py-0.5 text-xs font-medium text-warning">не отмечено {lesson.unmarked}</span>
            : done ? <span className="rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700">готово</span> : null}
          <ChevronDown className={cn('size-4 text-ink-muted transition-transform', expanded && 'rotate-180')} aria-hidden />
        </span>
      </button>
      {expanded ? <Roster lesson={lesson} /> : null}
    </li>
  )
}

/** Operational attendance: today's lessons as compact rows; open one to mark or correct. No KPI. */
export function AssistantAttendancePage() {
  const [params, setParams] = useSearchParams()
  const [date, setDate] = useState(params.get('date') ?? todayIso())
  const [group, setGroup] = useState(params.get('group') ?? '')
  const unmarked = params.get('unmarked') === '1'
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const { data: options } = useAssistantOptions()
  const { data, isPending, isError, refetch } = useAssistantAttendance({ date, group: group ? Number(group) : undefined, unmarked: unmarked || undefined })
  const shift = (days: number) => setDate(format(addDays(parseISO(date), days), 'yyyy-MM-dd'))
  const lessons = data?.lessons ?? []

  // A single lesson (one group, or a lesson opened from elsewhere) opens right away.
  useEffect(() => {
    if (lessons.length === 1) setExpanded(new Set([lessons[0].id]))
  }, [lessons])

  const toggle = (id: number) => setExpanded((current) => {
    const next = new Set(current)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  })

  return (
    <div>
      <PageHeader
        title="Посещаемость"
        description={unmarked ? 'Прошедшие занятия за 3 дня, где посещаемость не отмечена' : format(parseISO(date), 'd MMMM yyyy, EEEE', { locale: ru })}
      />
      <FilterBar className="mb-4">
        {unmarked ? (
          <Button variant="secondary" onClick={() => setParams({}, { replace: true })}>← К занятиям дня</Button>
        ) : (
          <div className="flex items-center gap-1">
            <Button variant="secondary" aria-label="Предыдущий день" onClick={() => shift(-1)}><ChevronLeft className="size-4" aria-hidden /></Button>
            <DatePicker aria-label="Дата" value={date} onChange={(e) => e.target.value && setDate(e.target.value)} className="w-40" />
            <Button variant="secondary" aria-label="Следующий день" onClick={() => shift(1)}><ChevronRight className="size-4" aria-hidden /></Button>
            {date !== todayIso() ? <Button variant="ghost" onClick={() => setDate(todayIso())}>Сегодня</Button> : null}
          </div>
        )}
        <FilterField>
          <Select aria-label="Группа" value={group} placeholder="Все группы" onChange={(e) => setGroup(e.target.value)} options={(options?.groups ?? []).map((g) => ({ value: String(g.id), label: g.name }))} />
        </FilterField>
      </FilterBar>
      {isPending ? <LoadingState label="Загружаем занятия…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}
      {data && lessons.length === 0 ? (
        <EmptyState icon={ClipboardCheck} title={unmarked ? 'Все прошедшие занятия отмечены' : 'В этот день занятий нет'} />
      ) : null}
      <ul className="space-y-2">
        {lessons.map((lesson) => (
          <LessonRow key={lesson.id} lesson={lesson} expanded={expanded.has(lesson.id)} onToggle={() => toggle(lesson.id)} showDate={unmarked} />
        ))}
      </ul>
    </div>
  )
}
