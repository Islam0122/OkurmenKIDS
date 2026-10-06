import { useEffect, useState } from 'react'
import { addDays, format, parseISO } from 'date-fns'
import { ru } from 'date-fns/locale'
import { ChevronDown, ChevronLeft, ChevronRight, ClipboardCheck, Eye } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { DatePicker } from '@/components/ui/DatePicker'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { LoadingState } from '@/components/ui/LoadingState'
import { Select } from '@/components/ui/Select'
import { useAssistantAttendance, useAssistantOptions } from '@/hooks/useAssistant'
import type { AttendanceLesson } from '@/types/assistant'
import { cn } from '@/utils/cn'

import { useAssistantActions } from '../actions/AssistantActions'
import { AttendanceBadge } from '../records/badges'
import { todayIso } from '../ui'

/** The roster of one lesson — read only: who came, as badges. Marks are
 * the trainer's record; the Assistant only looks. */
function Roster({ lesson }: { lesson: AttendanceLesson }) {
  const { open } = useAssistantActions()
  if (lesson.records.length === 0) return <p className="border-t border-border px-4 py-3 text-sm text-ink-secondary">В группе нет активных студентов.</p>
  return (
    <div className="border-t border-border bg-surface-muted/40">
      <ul className="grid divide-y divide-border sm:grid-cols-2 sm:divide-y-0">
        {lesson.records.map((record) => (
          <li key={record.student.id} className="flex items-center justify-between gap-3 border-border px-4 py-1.5 sm:border-b">
            <span className="min-w-0 truncate text-sm text-ink">{record.student.name}</span>
            <AttendanceBadge status={record.status} />
          </li>
        ))}
      </ul>
      <div className="flex items-center justify-between gap-2 border-t border-border px-4 py-2">
        <span className="flex items-center gap-1.5 text-xs text-ink-muted"><Eye className="size-3.5" aria-hidden />Только просмотр — отмечает тренер.</span>
        <Button size="sm" variant="ghost" onClick={() => open({ type: 'lesson-detail', lessonId: lesson.id })}>Подробнее</Button>
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

/** Operational attendance, read only: the day's lessons as compact rows; open one to see who came. No KPI. */
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
