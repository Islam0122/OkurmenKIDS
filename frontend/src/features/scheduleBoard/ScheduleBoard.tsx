import { useEffect, useMemo, useState } from 'react'
import { addDays, eachDayOfInterval, format, getDay, isToday, parseISO } from 'date-fns'
import { ru } from 'date-fns/locale'
import {
  AlertTriangle, CalendarClock, CalendarPlus, ChevronDown, ChevronLeft, ChevronRight, DoorOpen, Eye, FilterX, Loader2, ShieldCheck, SlidersHorizontal,
} from 'lucide-react'

import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { DatePicker } from '@/components/ui/DatePicker'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { useScheduleBoard, useScheduleOptions } from '@/hooks/useSchedule'
import type { DayOfWeek } from '@/types/common'
import type { BoardConflict, BoardLesson, LegendItem, ScheduleBoardData } from '@/types/schedule'
import { cn } from '@/utils/cn'

import { AgendaList } from './AgendaList'
import { FreeRoomsPanel } from './FreeRoomsPanel'
import { TrainerDot } from './LessonCard'
import { RoomFilter } from './RoomFilter'
import { TimeGrid } from './TimeGrid'
import type { GridColumn } from './TimeGrid'
import { DAY_END, formatDuration, fromMinutes, toMinutes } from './timeGrid'
import { useBoardState } from './useBoardState'
import type { BoardView } from './useBoardState'

const VIEWS: { value: BoardView; label: string }[] = [
  { value: 'day', label: 'День' },
  { value: 'week', label: 'Неделя' },
]
const WEEKDAY_CODES: DayOfWeek[] = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']
const iso = (date: Date) => format(date, 'yyyy-MM-dd')

/** Where «Добавить занятие» starts from — a clicked free spot, or nothing. */
export interface AddLessonPreset {
  date: string
  day: DayOfWeek
  start: string
  end: string
  room: number | null
}

export interface ScheduleBoardProps {
  /** sessionStorage key: each page remembers its own view and filters. */
  storageKey: string
  description?: string
  /** Click on a lesson; `canEdit` — the user may move / cancel it. */
  onOpenLesson: (lesson: BoardLesson, canEdit: boolean) => void
  /** «Добавить занятие» — offered only when the backend says the user can edit. */
  onAddLesson?: (preset?: AddLessonPreset) => void
}

/** The server's «now» (project time zone, Asia/Bishkek), kept ticking each minute. */
export function useServerNow(now: ScheduleBoardData['now'] | undefined, receivedAt: number) {
  const [tick, setTick] = useState(() => Date.now())
  useEffect(() => {
    const id = window.setInterval(() => setTick(Date.now()), 60_000)
    return () => window.clearInterval(id)
  }, [])
  return useMemo(() => {
    if (!now) return null
    const elapsed = Math.max(0, Math.floor((tick - receivedAt) / 60_000))
    const minutes = toMinutes(now.time) + elapsed
    if (minutes >= 24 * 60) return { date: iso(addDays(parseISO(now.date), 1)), minutes: minutes - 24 * 60 }
    return { date: now.date, minutes }
  }, [now, receivedAt, tick])
}

export function ScheduleBoard({ storageKey, description, onOpenLesson, onAddLesson }: ScheduleBoardProps) {
  const { state, update, clearFilters, range, shift, hasFilters } = useBoardState(storageKey)
  const [freeRoomsOpen, setFreeRoomsOpen] = useState(false)
  const [conflictsOpen, setConflictsOpen] = useState(false)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const { data: options } = useScheduleOptions()
  const { data, isPending, isFetching, isError, refetch, dataUpdatedAt } = useScheduleBoard({
    start: range.start,
    end: range.end,
    teacher: state.teacher ?? undefined,
    room: state.rooms.length ? state.rooms : undefined,
    group: state.group ?? undefined,
  })
  const now = useServerNow(data?.now, dataUpdatedAt)
  const activeFilters = (state.teacher !== null ? 1 : 0) + (state.group !== null ? 1 : 0) + (state.rooms.length ? 1 : 0)
  const canEdit = Boolean(data?.capabilities.can_edit && onAddLesson)
  // keepPreviousData shows the old period while the new one loads — never act on it as if it were current.
  const stale = data !== undefined && (data.start !== range.start || data.end !== range.end)
  const lessons = data?.lessons ?? []

  const days = useMemo(() => eachDayOfInterval({ start: parseISO(range.start), end: parseISO(range.end) }).map(iso), [range])
  const openLesson = (lesson: BoardLesson) => onOpenLesson(lesson, Boolean(data?.capabilities.can_edit))
  const addAt = (date: string, start: string, room: number | null) =>
    onAddLesson?.({ date, day: WEEKDAY_CODES[getDay(parseISO(date))], start, end: fromMinutes(Math.min(toMinutes(start) + 90, DAY_END - 1)), room })

  const columns: GridColumn[] = useMemo(() => {
    if (state.view === 'week') {
      return days.map((day) => ({
        key: day,
        header: (
          <button type="button" onClick={() => update({ view: 'day', date: day })} className="flex w-full items-baseline gap-1.5 text-left hover:text-brand-700" title="Открыть день">
            <span className={cn('text-xs font-semibold uppercase', isToday(parseISO(day)) ? 'text-brand-700' : 'text-ink-secondary')}>{format(parseISO(day), 'EEEEEE', { locale: ru })}</span>
            <span className={cn('rounded-full px-1.5 text-sm font-semibold', isToday(parseISO(day)) ? 'bg-brand-500 text-white' : 'text-ink')}>{format(parseISO(day), 'd')}</span>
            <span className="ml-auto text-2xs text-ink-muted">{lessons.filter((l) => l.date === day && l.status !== 'cancelled').length || ''}</span>
          </button>
        ),
        lessons: lessons.filter((l) => l.date === day),
        highlighted: now?.date === day,
        showNow: now?.date === day,
        onEmptyClick: canEdit ? (start) => addAt(day, start, null) : undefined,
        onCrowdClick: () => update({ view: 'day', date: day }),
      }))
    }
    // Day view: a column per room — busy and free rooms side by side.
    const all = options?.rooms ?? []
    const used = new Map(lessons.filter((l) => l.room).map((l) => [l.room!.id, l.room!.name]))
    let rooms: { id: number; name: string }[]
    if (state.rooms.length) rooms = state.rooms.map((id) => ({ id, name: all.find((r) => r.id === id)?.name ?? used.get(id) ?? `#${id}` }))
    else if (state.teacher !== null || state.group !== null) rooms = all.filter((r) => used.has(r.id))
    else rooms = [...all]
    for (const [id, name] of used) if (!rooms.some((r) => r.id === id)) rooms.push({ id, name })
    const result: GridColumn[] = rooms.map((room) => {
      const roomLessons = lessons.filter((l) => l.room?.id === room.id)
      const busy = roomLessons.filter((l) => l.status !== 'cancelled')
      const busyNow = now?.date === state.date && busy.some((l) => toMinutes(l.start) <= now.minutes && now.minutes < (toMinutes(l.end) || DAY_END))
      return {
        key: `room-${room.id}`,
        header: (
          <div className="flex min-w-0 items-center gap-1.5">
            <DoorOpen className="size-3.5 shrink-0 text-ink-muted" aria-hidden />
            <span className="truncate text-sm font-semibold text-ink">{room.name}</span>
            {now?.date === state.date ? (
              <span className={cn('ml-auto shrink-0 rounded-full px-1.5 text-2xs font-medium', busyNow ? 'bg-danger-soft text-danger' : 'bg-brand-50 text-brand-700')}>
                {busyNow ? 'занят' : 'свободен'}
              </span>
            ) : (
              <span className="ml-auto shrink-0 text-2xs text-ink-muted">{busy.length ? `${busy.length} зан.` : 'свободен'}</span>
            )}
          </div>
        ),
        lessons: roomLessons,
        showNow: now?.date === state.date,
        onEmptyClick: canEdit ? (start: string) => addAt(state.date, start, room.id) : undefined,
      }
    })
    const roomless = lessons.filter((l) => !l.room)
    if (roomless.length || result.length === 0) {
      result.push({
        key: 'no-room',
        header: <span className="text-sm font-semibold text-ink-secondary">{result.length ? 'Без кабинета' : 'Занятия'}</span>,
        lessons: roomless,
        showNow: now?.date === state.date,
        onEmptyClick: canEdit ? (start: string) => addAt(state.date, start, null) : undefined,
      })
    }
    return result
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.view, state.date, state.rooms, state.teacher, state.group, days, lessons, options, now, canEdit])

  const scrollTarget = useMemo(() => {
    if (now && days.includes(now.date)) return now.minutes
    const first = lessons.filter((l) => l.status !== 'cancelled').map((l) => toMinutes(l.start)).sort((a, b) => a - b)[0]
    return first ?? 8 * 60
  }, [now, days, lessons])

  const title = state.view === 'day'
    ? format(parseISO(state.date), 'EEEE, d MMMM yyyy', { locale: ru })
    : `${format(parseISO(range.start), 'd MMM', { locale: ru })} – ${format(parseISO(range.end), 'd MMM yyyy', { locale: ru })}`

  const teacherOptions = (options?.teachers ?? []).map((t) => ({ value: String(t.id), label: t.name }))
  const groupOptions = (options?.groups ?? []).map((g) => ({ value: String(g.id), label: `${g.name} — ${g.course}` }))
  const selectedTeacher = options?.teachers.find((t) => t.id === state.teacher)

  return (
    <div>
      <PageHeader
        title="Расписание"
        description={description}
        badge={data && !data.capabilities.can_edit ? <Badge tone="info"><Eye className="size-3.5" aria-hidden />Только просмотр</Badge> : null}
        actions={
          <>
            <Button variant="secondary" leftIcon={<DoorOpen className="size-4" aria-hidden />} onClick={() => setFreeRoomsOpen(true)} aria-label="Свободные кабинеты">
              <span className="sm:hidden">Кабинеты</span><span className="hidden sm:inline">Свободные кабинеты</span>
            </Button>
            {canEdit ? (
              <Button leftIcon={<CalendarPlus className="size-4" aria-hidden />} onClick={() => onAddLesson?.()} aria-label="Добавить занятие">
                <span className="sm:hidden">Занятие</span><span className="hidden sm:inline">Добавить занятие</span>
              </Button>
            ) : null}
          </>
        }
      />

      {/* Period navigation */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1">
          <Button variant="secondary" className="w-10 px-0" aria-label={state.view === 'day' ? 'Предыдущий день' : 'Предыдущая неделя'} onClick={() => shift(-1)}><ChevronLeft className="size-4" aria-hidden /></Button>
          <Button variant="secondary" onClick={() => update({ date: iso(new Date()) })}>Сегодня</Button>
          <Button variant="secondary" className="w-10 px-0" aria-label={state.view === 'day' ? 'Следующий день' : 'Следующая неделя'} onClick={() => shift(1)}><ChevronRight className="size-4" aria-hidden /></Button>
        </div>
        <DatePicker aria-label="Дата" className="w-36 sm:w-40" value={state.date} onChange={(e) => e.target.value && update({ date: e.target.value })} />
        <h2 className="order-last w-full min-w-0 text-base font-semibold text-ink first-letter:uppercase sm:order-none sm:w-auto">
          {title}
          {isFetching && data ? <Loader2 className="ml-2 inline size-4 animate-spin text-ink-muted" aria-label="Обновляем" /> : null}
        </h2>
        <SegmentedControl className="ml-auto" aria-label="Вид расписания" options={VIEWS} value={state.view} onChange={(view) => update({ view })} />
      </div>

      {/* Phones: filters fold away behind one button */}
      <button type="button" onClick={() => setFiltersOpen((v) => !v)} aria-expanded={filtersOpen}
        className="mb-2 inline-flex h-9 items-center gap-1.5 rounded-lg border border-border bg-surface px-3 text-sm font-medium text-ink md:hidden">
        <SlidersHorizontal className="size-4" aria-hidden />Фильтры{activeFilters ? <span className="rounded-full bg-brand-500 px-1.5 text-2xs text-white">{activeFilters}</span> : null}
        <ChevronDown className={cn('size-4 transition-transform', filtersOpen && 'rotate-180')} aria-hidden />
      </button>
      {/* Filters — each applies immediately */}
      <div className={cn('mb-3 grid-cols-1 gap-2 min-[480px]:grid-cols-2 md:grid lg:grid-cols-[repeat(3,minmax(0,15rem))_auto]', filtersOpen ? 'grid' : 'hidden')}>
        <div className="relative min-w-0">
          {selectedTeacher ? <TrainerDot color={selectedTeacher.color} className="pointer-events-none absolute top-1/2 left-3 z-10 -translate-y-1/2" /> : null}
          <Select aria-label="Тренер" className={cn(selectedTeacher && 'border-brand-500 pl-8')} value={state.teacher ? String(state.teacher) : ''} placeholder="Все тренеры"
            onChange={(e) => update({ teacher: e.target.value ? Number(e.target.value) : null })} options={teacherOptions} />
        </div>
        <RoomFilter rooms={options?.rooms ?? []} value={state.rooms} onChange={(rooms) => update({ rooms })} />
        <Select aria-label="Группа" className={cn(state.group && 'border-brand-500')} value={state.group ? String(state.group) : ''} placeholder="Все группы"
          onChange={(e) => update({ group: e.target.value ? Number(e.target.value) : null })} options={groupOptions} />
        {hasFilters ? (
          <Button variant="ghost" leftIcon={<FilterX className="size-4" aria-hidden />} onClick={clearFilters} className="justify-self-start">Очистить фильтры</Button>
        ) : null}
      </div>

      {data ? (
        <StatsBar
          data={data}
          conflictsOpen={conflictsOpen}
          onToggleConflicts={() => setConflictsOpen((v) => !v)}
          onFreeRooms={() => setFreeRoomsOpen(true)}
          activeTeacher={state.teacher}
          onTeacher={(id) => update({ teacher: state.teacher === id ? null : id })}
        />
      ) : null}
      {data && conflictsOpen && data.conflicts.length ? <ConflictsList conflicts={data.conflicts} lessons={lessons} onOpen={openLesson} multiDay={days.length > 1} /> : null}

      {isPending ? <LoadingState label="Загружаем расписание…" /> : null}
      {isError && !data ? <ErrorState onRetry={() => void refetch()} /> : null}
      {isError && data ? (
        <p role="alert" className="mb-3 rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">
          Не удалось обновить расписание — показаны последние загруженные данные. <button type="button" className="font-medium underline" onClick={() => void refetch()}>Повторить</button>
        </p>
      ) : null}

      {data ? (
        <div className={cn('transition-opacity', stale && 'opacity-50')} aria-busy={stale}>
          {lessons.length === 0 && !stale ? (
            <div className="mb-3 flex flex-wrap items-center gap-3 rounded-lg border border-dashed border-border-strong bg-surface px-4 py-3 text-sm text-ink-secondary">
              <CalendarClock className="size-5 text-ink-muted" aria-hidden />
              <span>{hasFilters ? 'По выбранным фильтрам занятий нет.' : state.view === 'day' ? 'В этот день занятий нет — все кабинеты свободны.' : 'На этой неделе занятий нет.'}</span>
              {hasFilters ? <Button size="sm" variant="secondary" onClick={clearFilters}>Очистить фильтры</Button> : null}
              {canEdit ? <Button size="sm" variant="secondary" leftIcon={<CalendarPlus className="size-4" aria-hidden />} onClick={() => onAddLesson?.()}>Добавить занятие</Button> : null}
            </div>
          ) : null}
          <div className="hidden md:block">
            <TimeGrid
              columns={columns}
              nowMinutes={now && days.includes(now.date) ? now.minutes : null}
              onOpen={openLesson}
              scrollTo={scrollTarget}
              showRoom={state.view === 'week'}
              minColumnWidth={state.view === 'week' ? 118 : 132}
              maxLanes={state.view === 'week' ? 3 : Infinity}
            />
            {canEdit ? <p className="mt-1.5 text-xs text-ink-muted">Нажмите на свободное место в сетке, чтобы добавить занятие на это время{state.view === 'day' ? ' и в этот кабинет' : ''}.</p> : null}
          </div>
          <div className="md:hidden">
            <AgendaList lessons={lessons} days={days} now={now} onOpen={openLesson} />
          </div>
        </div>
      ) : null}

      {freeRoomsOpen ? (
        <FreeRoomsPanel
          isOpen
          onClose={() => setFreeRoomsOpen(false)}
          initialDate={state.date}
          now={now}
          onShowRoom={(roomId, date) => update({ rooms: [roomId], date, view: 'day' })}
        />
      ) : null}
    </div>
  )
}

function StatsBar({ data, conflictsOpen, onToggleConflicts, onFreeRooms, activeTeacher, onTeacher }: {
  data: ScheduleBoardData
  conflictsOpen: boolean
  onToggleConflicts: () => void
  onFreeRooms: () => void
  activeTeacher: number | null
  onTeacher: (id: number) => void
}) {
  const { stats } = data
  const free = stats.free_rooms
  const chip = 'inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-sm whitespace-nowrap'
  return (
    <div className="mb-3 space-y-2">
      <div className="flex flex-wrap items-center gap-2" aria-live="polite">
        <span className={cn(chip, 'border-border bg-surface text-ink')}>
          <CalendarClock className="size-4 text-ink-muted" aria-hidden />
          <strong className="tabular-nums">{stats.lessons}</strong> {plural(stats.lessons, 'занятие', 'занятия', 'занятий')}
          {stats.minutes ? <span className="text-ink-secondary">· {formatDuration(stats.minutes)}</span> : null}
        </span>
        {free ? (
          <button type="button" onClick={onFreeRooms} className={cn(chip, 'border-brand-200 bg-brand-50 text-brand-700 hover:bg-brand-100')}>
            <DoorOpen className="size-4" aria-hidden />
            {free.mode === 'now' ? `Свободно сейчас (${free.at}):` : 'Кабинетов без занятий:'} <strong className="tabular-nums">{free.free} из {free.total}</strong>
          </button>
        ) : null}
        {stats.conflicts ? (
          <button type="button" onClick={onToggleConflicts} aria-expanded={conflictsOpen} className={cn(chip, 'border-danger/30 bg-danger-soft font-medium text-danger')}>
            <AlertTriangle className="size-4" aria-hidden />Конфликты: {stats.conflicts}
            <ChevronDown className={cn('size-4 transition-transform', conflictsOpen && 'rotate-180')} aria-hidden />
          </button>
        ) : stats.lessons ? (
          <span className={cn(chip, 'border-border bg-surface text-ink-secondary')}><ShieldCheck className="size-4 text-brand-600" aria-hidden />Без конфликтов</span>
        ) : null}
      </div>
      {data.legend.length ? <Legend items={data.legend} active={activeTeacher} onPick={onTeacher} /> : null}
    </div>
  )
}

function Legend({ items, active, onPick }: { items: LegendItem[]; active: number | null; onPick: (id: number) => void }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5" aria-label="Тренеры и их цвета">
      <span className="mr-1 text-xs font-medium text-ink-muted">Тренеры:</span>
      {items.map((item) => (
        <button key={item.id} type="button" onClick={() => onPick(item.id)} aria-pressed={active === item.id}
          title={active === item.id ? 'Показать всех тренеров' : `Только занятия: ${item.name}`}
          className={cn(
            'inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-xs text-ink transition-colors',
            active === item.id ? 'border-ink/30 bg-surface-hover font-semibold' : 'border-border bg-surface hover:bg-surface-hover',
            active !== null && active !== item.id && 'opacity-60',
          )}>
          <TrainerDot color={item.color} />
          {item.name}
          <span className="text-ink-muted tabular-nums">{item.lessons_count}</span>
        </button>
      ))}
    </div>
  )
}

function ConflictsList({ conflicts, lessons, onOpen, multiDay }: { conflicts: BoardConflict[]; lessons: BoardLesson[]; onOpen: (lesson: BoardLesson) => void; multiDay: boolean }) {
  const byId = new Map(lessons.map((l) => [l.id, l]))
  return (
    <section className="mb-3 rounded-xl border border-danger/30 bg-danger-soft/40 p-3" aria-label="Конфликты в расписании">
      <p className="mb-2 text-sm text-ink-secondary">Тренер, кабинет или группа заняты дважды в одно время. Нажмите на занятие, чтобы перенести его.</p>
      <ul className="grid gap-2 lg:grid-cols-2">
        {conflicts.map((conflict, index) => (
          <li key={index} className="rounded-lg bg-surface px-3 py-2 text-sm shadow-xs">
            <p className="font-medium text-danger">
              <AlertTriangle className="mr-1 inline size-4" aria-hidden />
              {conflict.kind_label} «{conflict.name}»{multiDay ? ` · ${format(parseISO(conflict.date), 'EEEEEE d MMM', { locale: ru })}` : ''}
            </p>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {conflict.lessons.map((ref) => {
                const lesson = byId.get(ref.id)
                return (
                  <button key={ref.id} type="button" disabled={!lesson} onClick={() => lesson && onOpen(lesson)}
                    className="rounded-md border border-border px-2 py-1 text-xs text-ink hover:bg-surface-hover disabled:cursor-default disabled:opacity-70"
                    title={lesson ? 'Открыть занятие' : 'Скрыто фильтром'}>
                    <span className="font-semibold">{ref.group.name}</span> {ref.start}–{ref.end}
                    {ref.teacher ? ` · ${ref.teacher.name}` : ''}{ref.room ? ` · ${ref.room.name}` : ''}
                  </button>
                )
              })}
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}

function plural(n: number, one: string, few: string, many: string) {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return one
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few
  return many
}
