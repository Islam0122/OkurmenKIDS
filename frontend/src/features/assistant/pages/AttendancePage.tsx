import { useEffect, useState } from 'react'
import { addDays, format, parseISO } from 'date-fns'
import { ru } from 'date-fns/locale'
import { Check, ChevronLeft, ChevronRight, ClipboardCheck, Clock, ShieldCheck, X } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'

import { assistantApi } from '@/api/assistant'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
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

function LessonAttendance({ lesson }: { lesson: AttendanceLesson }) {
  const [marks, setMarks] = useState<Record<number, AttendanceStatus | null>>({})
  useEffect(() => {
    setMarks(Object.fromEntries(lesson.records.map((r) => [r.student.id, r.status])))
  }, [lesson])
  const changed = lesson.records.filter((r) => marks[r.student.id] && marks[r.student.id] !== r.status)
  const save = useAssistantMutation(
    () => assistantApi.markAttendance(lesson.id, changed.map((r) => ({ student: r.student.id, status: marks[r.student.id] as AttendanceStatus }))),
    `${lesson.group.name}: посещаемость сохранена`,
  )
  const present = Object.values(marks).filter((m) => m === 'present' || m === 'late').length
  const absent = Object.values(marks).filter((m) => m === 'absent' || m === 'excused').length
  const allPresent = () => setMarks(Object.fromEntries(lesson.records.map((r) => [r.student.id, marks[r.student.id] ?? 'present'])))

  return (
    <Card
      title={`${lesson.group.name} · ${lesson.start}–${lesson.end}`}
      description={`${lesson.subject?.name ?? '—'} · ${lesson.teacher?.name ?? '—'}`}
      actions={<span className="text-right text-sm text-ink-secondary">Были: <b className="text-brand-700">{present}</b> · Нет: <b className="text-danger">{absent}</b></span>}
    >
      {lesson.records.length === 0 ? <p className="text-sm text-ink-secondary">В группе нет активных студентов.</p> : (
        <ul className="divide-y divide-border">
          {lesson.records.map((record) => (
            <li key={record.student.id} className="flex flex-col gap-2 py-2.5 sm:flex-row sm:items-center sm:justify-between">
              <span className="min-w-0 truncate text-sm font-medium text-ink">{record.student.name}</span>
              <div className="flex gap-1" role="radiogroup" aria-label={`Отметка: ${record.student.name}`}>
                {MARKS.map((mark) => {
                  const active = marks[record.student.id] === mark.value
                  return (
                    <button key={mark.value} type="button" role="radio" aria-checked={active} title={mark.label} aria-label={mark.label}
                      onClick={() => setMarks((m) => ({ ...m, [record.student.id]: mark.value }))}
                      className={cn('flex size-9 items-center justify-center rounded-lg border transition-colors', active ? mark.active : 'border-border text-ink-muted hover:bg-surface-hover')}>
                      <mark.icon className="size-4" aria-hidden />
                    </button>
                  )
                })}
              </div>
            </li>
          ))}
        </ul>
      )}
      {lesson.records.length ? (
        <div className="mt-4 flex flex-col-reverse gap-2 border-t border-border pt-4 sm:flex-row sm:justify-end">
          <Button variant="secondary" onClick={allPresent}>Отметить остальных «был»</Button>
          <Button disabled={changed.length === 0 || save.isPending} isLoading={save.isPending} onClick={() => save.mutate(undefined)}>
            Сохранить{changed.length ? ` (${changed.length})` : ''}
          </Button>
        </div>
      ) : null}
    </Card>
  )
}

/** Operational attendance: the day's lessons, mark or correct who came. No KPI. */
export function AssistantAttendancePage() {
  const [params] = useSearchParams()
  const [date, setDate] = useState(todayIso())
  const [group, setGroup] = useState(params.get('group') ?? '')
  const { data: options } = useAssistantOptions()
  const { data, isPending, isError, refetch } = useAssistantAttendance({ date, group: group ? Number(group) : undefined })
  const shift = (days: number) => setDate(format(addDays(parseISO(date), days), 'yyyy-MM-dd'))

  return (
    <div>
      <PageHeader title="Посещаемость" description={format(parseISO(date), 'd MMMM yyyy, EEEE', { locale: ru })} />
      <FilterBar>
        <div className="flex items-center gap-1">
          <Button variant="secondary" aria-label="Предыдущий день" onClick={() => shift(-1)}><ChevronLeft className="size-4" aria-hidden /></Button>
          <DatePicker aria-label="Дата" value={date} onChange={(e) => e.target.value && setDate(e.target.value)} className="w-40" />
          <Button variant="secondary" aria-label="Следующий день" onClick={() => shift(1)}><ChevronRight className="size-4" aria-hidden /></Button>
        </div>
        <FilterField>
          <Select aria-label="Группа" value={group} placeholder="Все группы" onChange={(e) => setGroup(e.target.value)} options={(options?.groups ?? []).map((g) => ({ value: String(g.id), label: g.name }))} />
        </FilterField>
      </FilterBar>
      {isPending ? <LoadingState label="Загружаем занятия…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}
      {data && data.lessons.length === 0 ? <EmptyState icon={ClipboardCheck} title="В этот день занятий нет" /> : null}
      <div className="grid gap-6 xl:grid-cols-2">
        {data?.lessons.map((lesson) => <LessonAttendance key={lesson.id} lesson={lesson} />)}
      </div>
    </div>
  )
}
