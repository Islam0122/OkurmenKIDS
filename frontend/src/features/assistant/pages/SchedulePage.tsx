import { useMemo, useState } from 'react'
import {
  addDays, addMonths, eachDayOfInterval, endOfMonth, endOfWeek, format, isSameMonth, isToday, parseISO, startOfMonth, startOfWeek,
} from 'date-fns'
import { ru } from 'date-fns/locale'
import { AlertTriangle, CalendarClock, CalendarPlus, ChevronLeft, ChevronRight } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { LoadingState } from '@/components/ui/LoadingState'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { useAssistantOptions, useAssistantSchedule } from '@/hooks/useAssistant'
import type { AssistantLesson, ScheduleConflict } from '@/types/assistant'
import { cn } from '@/utils/cn'

import { useAssistantActions } from '../actions/AssistantActions'

type View = 'day' | 'week' | 'month'
const VIEWS: { value: View; label: string }[] = [
  { value: 'day', label: 'День' },
  { value: 'week', label: 'Неделя' },
  { value: 'month', label: 'Месяц' },
]
const WEEKDAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'] as const
const iso = (date: Date) => format(date, 'yyyy-MM-dd')

function range(view: View, anchor: Date): { start: Date; end: Date } {
  if (view === 'day') return { start: anchor, end: anchor }
  if (view === 'week') return { start: startOfWeek(anchor, { weekStartsOn: 1 }), end: endOfWeek(anchor, { weekStartsOn: 1 }) }
  return { start: startOfWeek(startOfMonth(anchor), { weekStartsOn: 1 }), end: endOfWeek(endOfMonth(anchor), { weekStartsOn: 1 }) }
}

/** One lesson in the grid: group, subject, trainer, time — click for details. */
export function LessonChip({ lesson, onOpen, showTime = true }: { lesson: AssistantLesson; onOpen: (lesson: AssistantLesson) => void; showTime?: boolean }) {
  return (
    <button
      type="button"
      onClick={() => onOpen(lesson)}
      title={`${lesson.group.name} · ${lesson.subject?.name ?? ''} · ${lesson.teacher?.name ?? ''} · ${lesson.start}–${lesson.end}`}
      className={cn(
        'w-full min-w-0 rounded-md border-l-[3px] px-2 py-1 text-left transition-colors hover:bg-brand-50',
        lesson.status === 'cancelled' ? 'border-danger bg-danger-soft/40 line-through'
          : lesson.status === 'completed' ? 'border-ink-muted bg-surface-muted' : 'border-brand-500 bg-brand-50/50',
      )}
    >
      <p className="flex items-baseline justify-between gap-1">
        <span className="truncate text-sm font-semibold text-ink">{lesson.group.name}</span>
        {showTime ? <span className="shrink-0 text-2xs font-medium text-ink-secondary tabular-nums">{lesson.start}–{lesson.end}</span> : null}
      </p>
      <p className="truncate text-xs text-ink-secondary">{lesson.subject?.name ?? '—'} · {lesson.teacher?.name ?? '—'}</p>
    </button>
  )
}

function ConflictsCard({ conflicts }: { conflicts: ScheduleConflict[] }) {
  return (
    <Card title="Конфликты в расписании" description="Один тренер, аудитория или группа заняты дважды в одно время." className="mb-4 border-danger/30">
      <ul className="grid gap-2 md:grid-cols-2">
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

/** Week as a timetable: rows are start times, columns are days. Phones get a per-day list. */
function WeekGrid({ days, lessons, onOpen, onDay }: { days: Date[]; lessons: AssistantLesson[]; onOpen: (l: AssistantLesson) => void; onDay: (d: Date) => void }) {
  const times = [...new Set(lessons.map((l) => l.start))].sort()
  const cell = new Map<string, AssistantLesson[]>()
  for (const lesson of lessons) {
    const key = `${lesson.date}|${lesson.start}`
    cell.set(key, [...(cell.get(key) ?? []), lesson])
  }
  if (lessons.length === 0) return <EmptyState icon={CalendarClock} title="На этой неделе занятий нет" />
  return (
    <>
      <div className="card hidden overflow-x-auto md:block">
        <table className="w-full min-w-[760px] table-fixed border-collapse text-sm">
          <thead>
            <tr className="border-b border-border bg-surface-muted">
              <th className="w-16 px-2 py-2 text-left text-xs font-semibold text-ink-secondary">Время</th>
              {days.map((day) => (
                <th key={iso(day)} className="px-1.5 py-2 text-left">
                  <button type="button" onClick={() => onDay(day)} className={cn('text-xs font-semibold uppercase hover:text-brand-700', isToday(day) ? 'text-brand-700' : 'text-ink-secondary')}>
                    {format(day, 'EEEEEE', { locale: ru })} <span className={cn('ml-0.5 rounded-full px-1.5 py-0.5', isToday(day) && 'bg-brand-500 text-white')}>{format(day, 'd')}</span>
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {times.map((time) => (
              <tr key={time} className="border-b border-border last:border-0">
                <td className="px-2 py-1.5 align-top text-xs font-semibold text-ink tabular-nums">{time}</td>
                {days.map((day) => (
                  <td key={iso(day)} className={cn('px-1 py-1 align-top', isToday(day) && 'bg-brand-50/40')}>
                    <div className="space-y-1">
                      {(cell.get(`${iso(day)}|${time}`) ?? []).map((lesson) => <LessonChip key={lesson.id} lesson={lesson} onOpen={onOpen} showTime={false} />)}
                    </div>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="space-y-3 md:hidden">
        {days.map((day) => {
          const dayLessons = lessons.filter((l) => l.date === iso(day))
          if (dayLessons.length === 0) return null
          return (
            <section key={iso(day)} className="card card-body">
              <h3 className={cn('mb-2 text-sm font-semibold first-letter:uppercase', isToday(day) ? 'text-brand-700' : 'text-ink')}>{format(day, 'EEEE, d MMMM', { locale: ru })}</h3>
              <div className="space-y-1.5">{dayLessons.map((lesson) => <LessonChip key={lesson.id} lesson={lesson} onOpen={onOpen} />)}</div>
            </section>
          )
        })}
      </div>
    </>
  )
}

export function AssistantSchedulePage() {
  const [params, setParams] = useSearchParams()
  const view = (VIEWS.some((v) => v.value === params.get('view')) ? params.get('view') : 'week') as View
  const [anchor, setAnchor] = useState(() => (params.get('date') ? parseISO(params.get('date') as string) : new Date()))
  const [group, setGroup] = useState(params.get('group') ?? '')
  const [teacher, setTeacher] = useState(params.get('teacher') ?? '')
  const [course, setCourse] = useState('')
  const [weekday, setWeekday] = useState('')
  const [showConflicts, setShowConflicts] = useState(params.get('conflicts') === '1')
  const { open } = useAssistantActions()
  const openLesson = (lesson: AssistantLesson) => open({ type: 'lesson', lesson })
  const { data: options } = useAssistantOptions()
  const { start, end } = range(view, anchor)
  const { data, isPending, isError, refetch } = useAssistantSchedule({
    start: iso(start), end: iso(end),
    group: group ? Number(group) : undefined, teacher: teacher ? Number(teacher) : undefined,
    course: course ? Number(course) : undefined, day: view !== 'day' && weekday ? weekday : undefined,
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
  const openDay = (day: Date) => { setAnchor(day); setView('day') }
  const title = view === 'day'
    ? format(anchor, 'd MMMM yyyy, EEEE', { locale: ru })
    : view === 'week' ? `${format(start, 'd MMM', { locale: ru })} – ${format(end, 'd MMM yyyy', { locale: ru })}` : format(anchor, 'LLLL yyyy', { locale: ru })
  const conflicts = data?.conflicts ?? []
  const days = eachDayOfInterval({ start, end })
  const dayLessons = byDay.get(iso(anchor)) ?? []

  return (
    <div>
      <PageHeader
        title="Расписание"
        description="Занятия всех групп. Нажмите на занятие — перенос, отмена, посещаемость."
        actions={<Button leftIcon={<CalendarPlus className="size-4" aria-hidden />} onClick={() => open({ type: 'schedule' })}>Расписание</Button>}
      />
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <SegmentedControl aria-label="Вид" options={VIEWS} value={view} onChange={setView} />
        <div className="flex items-center gap-1">
          <Button variant="secondary" aria-label="Назад" onClick={() => shift(-1)}><ChevronLeft className="size-4" aria-hidden /></Button>
          <Button variant="secondary" onClick={() => setAnchor(new Date())}>Сегодня</Button>
          <Button variant="secondary" aria-label="Вперёд" onClick={() => shift(1)}><ChevronRight className="size-4" aria-hidden /></Button>
        </div>
        <h2 className="ml-1 text-base font-semibold text-ink first-letter:uppercase">{title}</h2>
        {conflicts.length ? (
          <button type="button" onClick={() => setShowConflicts((v) => !v)} className="ml-auto inline-flex h-9 items-center gap-1.5 rounded-lg border border-danger/30 bg-danger-soft px-3 text-sm font-medium text-danger">
            <AlertTriangle className="size-4" aria-hidden /> Конфликты: {conflicts.length}
          </button>
        ) : null}
      </div>
      <FilterBar className="mb-4">
        <FilterField>
          <Select aria-label="Группа" value={group} placeholder="Все группы" onChange={(e) => setGroup(e.target.value)} options={(options?.groups ?? []).map((g) => ({ value: String(g.id), label: g.name }))} />
        </FilterField>
        <FilterField>
          <Select aria-label="Тренер" value={teacher} placeholder="Все тренеры" onChange={(e) => setTeacher(e.target.value)} options={(options?.teachers ?? []).map((t) => ({ value: String(t.id), label: t.name }))} />
        </FilterField>
        <FilterField>
          <Select aria-label="Программа" value={course} placeholder="Все программы" onChange={(e) => setCourse(e.target.value)} options={(options?.courses ?? []).map((c) => ({ value: String(c.id), label: c.name }))} />
        </FilterField>
        {view !== 'day' ? (
          <FilterField>
            <Select aria-label="День недели" value={weekday} placeholder="Все дни" onChange={(e) => setWeekday(e.target.value)}
              options={WEEKDAYS.map((code) => ({ value: code, label: options?.weekdays.find((d) => d.code === code)?.label ?? code }))} />
          </FilterField>
        ) : null}
      </FilterBar>

      {showConflicts && conflicts.length ? <ConflictsCard conflicts={conflicts} /> : null}
      {isPending ? <LoadingState label="Загружаем расписание…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}

      {data && view === 'day' ? (
        dayLessons.length === 0 ? (
          <EmptyState icon={CalendarClock} title="В этот день занятий нет" action={<Button variant="secondary" leftIcon={<CalendarPlus className="size-4" aria-hidden />} onClick={() => open({ type: 'schedule' })}>Добавить расписание</Button>} />
        ) : (
          <div className="card divide-y divide-border">
            {dayLessons.map((lesson) => (
              <button key={lesson.id} type="button" onClick={() => openLesson(lesson)} className="flex w-full items-center gap-4 px-4 py-2.5 text-left hover:bg-surface-hover">
                <span className="w-24 shrink-0 text-sm font-semibold text-ink tabular-nums">{lesson.start}–{lesson.end}</span>
                <span className="w-24 shrink-0 truncate font-medium text-ink">{lesson.group.name}</span>
                <span className="min-w-0 flex-1 truncate text-sm text-ink-secondary">{lesson.subject?.name ?? '—'} · {lesson.teacher?.name ?? '—'}{lesson.room ? ` · ${lesson.room.name}` : ''}</span>
                <span className="hidden shrink-0 text-sm text-ink-secondary sm:inline">{lesson.students_count ?? 0} студ.</span>
                <span className={cn('hidden shrink-0 text-xs sm:inline', lesson.status === 'completed' ? 'text-brand-700' : 'text-ink-muted')}>{lesson.status_display}</span>
              </button>
            ))}
          </div>
        )
      ) : null}

      {data && view === 'week' ? <WeekGrid days={days} lessons={data.lessons} onOpen={openLesson} onDay={openDay} /> : null}

      {data && view === 'month' ? (
        <div className="card overflow-hidden">
          <div className="grid grid-cols-7 border-b border-border bg-surface-muted text-center text-xs font-semibold text-ink-secondary">
            {['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'].map((d) => <div key={d} className="py-2">{d}</div>)}
          </div>
          <div className="grid grid-cols-7">
            {days.map((day) => {
              const lessons = byDay.get(iso(day)) ?? []
              return (
                <button key={iso(day)} type="button" onClick={() => openDay(day)}
                  className={cn('flex min-h-16 min-w-0 flex-col items-start justify-start border-r border-b border-border p-1.5 text-left hover:bg-surface-hover sm:min-h-24', !isSameMonth(day, anchor) && 'bg-surface-muted/60 text-ink-muted')}>
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
    </div>
  )
}
