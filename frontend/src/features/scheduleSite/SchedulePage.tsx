import { useEffect, useMemo, useState } from 'react'
import { addDays, eachDayOfInterval, endOfWeek, format, isToday, isValid, parseISO, startOfWeek } from 'date-fns'
import { ru } from 'date-fns/locale'
import { CalendarClock, ChevronLeft, ChevronRight, DoorOpen, FilterX, Loader2, RefreshCw, Search, X } from 'lucide-react'
import { Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom'

import { Button } from '@/components/ui/Button'
import { DatePicker } from '@/components/ui/DatePicker'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { FreeRoomsPanel } from '@/features/scheduleBoard/FreeRoomsPanel'
import { TrainerDot } from '@/features/scheduleBoard/LessonCard'
import { ConflictNotes, LessonFacts } from '@/features/scheduleBoard/LessonPreviewModal'
import { RoomFilter } from '@/features/scheduleBoard/RoomFilter'
import { useServerNow } from '@/features/scheduleBoard/ScheduleBoard'
import { DAY_END, toMinutes } from '@/features/scheduleBoard/timeGrid'
import { useScheduleBoard, useScheduleOptions } from '@/hooks/useSchedule'
import type { BoardLesson } from '@/types/schedule'
import { cn } from '@/utils/cn'

import { FullGrid, FullLessonCard, WeekTable } from './FullGrid'
import type { SiteColumn } from './FullGrid'

export type SiteView = 'day' | 'week'

/** How often an open page re-reads the schedule (plus on window focus). */
export const REFRESH_MS = 60_000
const LAST_QUERY = 'okurmen.schedule-site.query'
const iso = (date: Date) => format(date, 'yyyy-MM-dd')
const num = (value: string | null) => (value && /^\d+$/.test(value) ? Number(value) : null)

/** /schedule → the last view the user had in this tab (or the day view). */
export function ScheduleIndex() {
  let target = '/schedule/day'
  try {
    target = sessionStorage.getItem(LAST_QUERY) ?? target
  } catch {
    // storage blocked — the day view
  }
  return <Navigate to={target.startsWith('/schedule/') ? target : '/schedule/day'} replace />
}

function matches(lesson: BoardLesson, query: string): boolean {
  const haystack = [lesson.group.name, lesson.teacher?.name, lesson.room?.name, lesson.subject?.name, lesson.course?.name, lesson.topic]
    .filter(Boolean).join(' ').toLowerCase()
  return query.toLowerCase().split(/\s+/).filter(Boolean).every((word) => haystack.includes(word))
}

export function SiteSchedulePage({ view }: { view: SiteView }) {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const location = useLocation()
  const rawDate = params.get('date')
  const date = rawDate && isValid(parseISO(rawDate)) ? rawDate : iso(new Date())
  const teacher = num(params.get('teacher'))
  const group = num(params.get('group'))
  const rooms = (params.get('room') ?? '').split(',').map(num).filter((n): n is number => n !== null)
  const query = params.get('q') ?? ''
  const [freeRoomsOpen, setFreeRoomsOpen] = useState(false)
  const [opened, setOpened] = useState<BoardLesson | null>(null)

  // The page's state is its URL: shareable, and kept when switching День / Неделя.
  useEffect(() => {
    try {
      sessionStorage.setItem(LAST_QUERY, `${location.pathname}${location.search}`)
    } catch {
      // ignore
    }
  }, [location.pathname, location.search])

  const set = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(patch)) {
      if (value === null || value === '') next.delete(key)
      else next.set(key, value)
    }
    setParams(next, { replace: true })
  }
  const switchView = (value: SiteView) => navigate({ pathname: `/schedule/${value}`, search: params.toString() })

  const range = useMemo(() => {
    if (view === 'day') return { start: date, end: date }
    const anchor = parseISO(date)
    return { start: iso(startOfWeek(anchor, { weekStartsOn: 1 })), end: iso(endOfWeek(anchor, { weekStartsOn: 1 })) }
  }, [view, date])
  const days = useMemo(() => eachDayOfInterval({ start: parseISO(range.start), end: parseISO(range.end) }).map(iso), [range])

  const { data: options } = useScheduleOptions()
  const { data, isPending, isFetching, isError, refetch, dataUpdatedAt } = useScheduleBoard(
    { start: range.start, end: range.end, teacher: teacher ?? undefined, group: group ?? undefined, room: rooms.length ? rooms : undefined },
    { refreshMs: REFRESH_MS },
  )
  const now = useServerNow(data?.now, dataUpdatedAt)
  const stale = data !== undefined && (data.start !== range.start || data.end !== range.end)
  const lessons = useMemo(() => (data?.lessons ?? []).filter((l) => !query || matches(l, query)), [data, query])
  const hasFilters = teacher !== null || group !== null || rooms.length > 0 || query !== ''

  const columns: SiteColumn[] = useMemo(() => {
    if (view === 'week') {
      return days.map((day) => ({
        key: day,
        header: (
          <button type="button" onClick={() => navigate({ pathname: '/schedule/day', search: new URLSearchParams({ ...Object.fromEntries(params), date: day }).toString() })}
            className="flex w-full items-baseline gap-1.5 text-left hover:text-brand-700" title="Открыть день">
            <span className={cn('text-xs font-semibold uppercase', isToday(parseISO(day)) ? 'text-brand-700' : 'text-ink-secondary')}>
              {format(parseISO(day), 'EEEEEE', { locale: ru })}
            </span>
            <span className={cn('rounded-full px-1.5 text-sm font-semibold', isToday(parseISO(day)) ? 'bg-brand-500 text-white' : 'text-ink')}>{format(parseISO(day), 'd MMM', { locale: ru })}</span>
            <span className="ml-auto text-xs text-ink-muted">{lessons.filter((l) => l.date === day && l.status !== 'cancelled').length || ''}</span>
          </button>
        ),
        lessons: lessons.filter((l) => l.date === day),
        highlighted: now?.date === day,
        showNow: now?.date === day,
      }))
    }
    const all = options?.rooms ?? []
    const used = new Map(lessons.filter((l) => l.room).map((l) => [l.room!.id, l.room!.name]))
    let list: { id: number; name: string }[]
    if (rooms.length) list = rooms.map((id) => ({ id, name: all.find((r) => r.id === id)?.name ?? used.get(id) ?? `#${id}` }))
    else if (teacher !== null || group !== null || query) list = all.filter((r) => used.has(r.id))
    else list = [...all]
    for (const [id, name] of used) if (!list.some((r) => r.id === id)) list.push({ id, name })
    const result: SiteColumn[] = list.map((room) => {
      const roomLessons = lessons.filter((l) => l.room?.id === room.id)
      const busyNow = now?.date === date && roomLessons.some((l) => l.status !== 'cancelled' && toMinutes(l.start) <= now.minutes && now.minutes < (toMinutes(l.end) || DAY_END))
      return {
        key: `room-${room.id}`,
        header: (
          <div className="flex items-center gap-1.5">
            <DoorOpen className="size-4 shrink-0 text-ink-muted" aria-hidden />
            <span className="text-sm font-semibold text-ink">{room.name}</span>
            {now?.date === date ? (
              <span className={cn('ml-auto rounded-full px-1.5 text-2xs font-medium', busyNow ? 'bg-danger-soft text-danger' : 'bg-brand-50 text-brand-700')}>
                {busyNow ? 'занят' : 'свободен'}
              </span>
            ) : null}
          </div>
        ),
        lessons: roomLessons,
        showNow: now?.date === date,
      }
    })
    const roomless = lessons.filter((l) => !l.room)
    if (roomless.length || result.length === 0) {
      result.push({ key: 'no-room', header: <span className="text-sm font-semibold text-ink-secondary">{result.length ? 'Без кабинета' : 'Занятия'}</span>, lessons: roomless, showNow: now?.date === date })
    }
    return result
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, days, lessons, options, now, date, teacher, group, query, rooms.join(',')])

  const firstStart = lessons.filter((l) => l.status !== 'cancelled').map((l) => toMinutes(l.start)).sort((a, b) => a - b)[0]
  const scrollTarget = now && days.includes(now.date) ? now.minutes : firstStart ?? 8 * 60
  const title = view === 'day'
    ? format(parseISO(date), 'EEEE, d MMMM yyyy', { locale: ru })
    : `${format(parseISO(range.start), 'd MMM', { locale: ru })} – ${format(parseISO(range.end), 'd MMM yyyy', { locale: ru })}`
  const live = lessons.filter((l) => l.status !== 'cancelled')

  return (
    <div>
      {/* Navigation */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1">
          <Button variant="secondary" className="w-10 px-0" aria-label={view === 'day' ? 'Предыдущий день' : 'Предыдущая неделя'}
            onClick={() => set({ date: iso(addDays(parseISO(date), view === 'day' ? -1 : -7)) })}><ChevronLeft className="size-4" aria-hidden /></Button>
          <Button variant="secondary" onClick={() => set({ date: null })}>Сегодня</Button>
          <Button variant="secondary" className="w-10 px-0" aria-label={view === 'day' ? 'Следующий день' : 'Следующая неделя'}
            onClick={() => set({ date: iso(addDays(parseISO(date), view === 'day' ? 1 : 7)) })}><ChevronRight className="size-4" aria-hidden /></Button>
        </div>
        <DatePicker aria-label="Дата" className="w-36 sm:w-40" value={date} onChange={(e) => e.target.value && set({ date: e.target.value })} />
        <SegmentedControl aria-label="Вид расписания" value={view} onChange={switchView}
          options={[{ value: 'day', label: 'День' }, { value: 'week', label: 'Неделя' }]} />
        <h1 className="order-last w-full text-lg font-semibold text-ink first-letter:uppercase lg:order-none lg:w-auto">{title}</h1>
        <div className="ml-auto flex items-center gap-2">
          <span className="hidden items-center gap-1 text-xs text-ink-muted md:inline-flex" title="Обновляется автоматически каждую минуту">
            {isFetching ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : <RefreshCw className="size-3.5" aria-hidden />}
            {dataUpdatedAt ? `обновлено ${format(dataUpdatedAt, 'HH:mm')}` : ''}
          </span>
          <Button leftIcon={<DoorOpen className="size-4" aria-hidden />} onClick={() => setFreeRoomsOpen(true)}>Свободные кабинеты</Button>
        </div>
      </div>

      {/* Filters and search — server-side filters, search over the loaded period */}
      <div className="mb-3 grid grid-cols-1 gap-2 min-[520px]:grid-cols-2 lg:grid-cols-[repeat(3,minmax(0,16rem))_minmax(0,18rem)_auto]">
        <Select aria-label="Тренер" value={teacher ? String(teacher) : ''} placeholder="Все тренеры" className={cn(teacher && 'border-brand-500')}
          onChange={(e) => set({ teacher: e.target.value || null })}
          options={(options?.teachers ?? []).map((t) => ({ value: String(t.id), label: t.name }))} />
        <RoomFilter rooms={options?.rooms ?? []} value={rooms} onChange={(next) => set({ room: next.length ? next.join(',') : null })} />
        <Select aria-label="Группа" value={group ? String(group) : ''} placeholder="Все группы" className={cn(group && 'border-brand-500')}
          onChange={(e) => set({ group: e.target.value || null })}
          options={(options?.groups ?? []).map((g) => ({ value: String(g.id), label: `${g.name} — ${g.course}` }))} />
        <label className="relative block">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-muted" aria-hidden />
          <input type="search" aria-label="Поиск" placeholder="Поиск: группа, тренер, кабинет…" value={query}
            onChange={(e) => set({ q: e.target.value || null })} className="form-control pl-9" />
          {query ? (
            <button type="button" aria-label="Очистить поиск" onClick={() => set({ q: null })} className="absolute top-1/2 right-2 -translate-y-1/2 rounded p-1 text-ink-muted hover:bg-surface-hover">
              <X className="size-4" aria-hidden />
            </button>
          ) : null}
        </label>
        {hasFilters ? (
          <Button variant="ghost" leftIcon={<FilterX className="size-4" aria-hidden />} className="justify-self-start"
            onClick={() => set({ teacher: null, group: null, room: null, q: null })}>Сбросить</Button>
        ) : null}
      </div>

      {data ? (
        <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          <span className="text-ink"><strong className="tabular-nums">{live.length}</strong> занятий{query ? ' по запросу' : ''}</span>
          {data.stats.free_rooms ? (
            <button type="button" onClick={() => setFreeRoomsOpen(true)} className="text-brand-700 hover:underline">
              {data.stats.free_rooms.mode === 'now' ? `Свободно сейчас: ${data.stats.free_rooms.free} из ${data.stats.free_rooms.total}` : `Кабинетов без занятий: ${data.stats.free_rooms.free} из ${data.stats.free_rooms.total}`}
            </button>
          ) : null}
          {data.legend.length ? (
            <span className="flex flex-wrap items-center gap-1.5" aria-label="Тренеры и их цвета">
              {data.legend.map((t) => (
                <button key={t.id} type="button" aria-pressed={teacher === t.id} onClick={() => set({ teacher: teacher === t.id ? null : String(t.id) })}
                  className={cn('inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs text-ink',
                    teacher === t.id ? 'border-ink/30 bg-surface-hover font-semibold' : 'border-border bg-surface hover:bg-surface-hover')}>
                  <TrainerDot color={t.color} />{t.name}
                </button>
              ))}
            </span>
          ) : null}
        </div>
      ) : null}

      {isPending ? <LoadingState label="Загружаем расписание…" /> : null}
      {isError && !data ? <ErrorState onRetry={() => void refetch()} /> : null}
      {isError && data ? (
        <p role="alert" className="mb-3 rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">
          Не удалось обновить данные — показано последнее загруженное расписание. <button type="button" className="font-medium underline" onClick={() => void refetch()}>Повторить</button>
        </p>
      ) : null}

      {data ? (
        <div className={cn('transition-opacity', stale && 'opacity-50')} aria-busy={stale}>
          {lessons.length === 0 && !stale ? (
            <div className="mb-3 flex items-center gap-3 rounded-lg border border-dashed border-border-strong bg-surface px-4 py-3 text-sm text-ink-secondary">
              <CalendarClock className="size-5 text-ink-muted" aria-hidden />
              {hasFilters ? 'По выбранным фильтрам занятий нет.' : view === 'day' ? 'В этот день занятий нет.' : 'На этой неделе занятий нет.'}
            </div>
          ) : null}
          <div className="hidden md:block">
            {view === 'day' ? (
              <FullGrid columns={columns} nowMinutes={now && days.includes(now.date) ? now.minutes : null} onOpen={setOpened}
                scrollTo={scrollTarget} />
            ) : (
              <WeekTable days={columns} lessons={lessons} onOpen={setOpened} nowDate={now?.date ?? null}
                nowMinutes={now && days.includes(now.date) ? now.minutes : null} />
            )}
          </div>
          <div className="space-y-3 md:hidden" data-testid="site-agenda">
            {days.map((day) => {
              const items = lessons.filter((l) => l.date === day)
              if (days.length > 1 && !items.length) return null
              return (
                <section key={day}>
                  <h2 className={cn('mb-1.5 text-sm font-semibold first-letter:uppercase', isToday(parseISO(day)) ? 'text-brand-700' : 'text-ink')}>
                    {format(parseISO(day), 'EEEE, d MMMM', { locale: ru })}
                  </h2>
                  {items.length ? (
                    <div className="space-y-2">{items.map((l) => <FullLessonCard key={l.id} lesson={l} onOpen={setOpened} className="w-full" />)}</div>
                  ) : <p className="text-sm text-ink-muted">Занятий нет</p>}
                </section>
              )
            })}
          </div>
        </div>
      ) : null}

      {opened ? (
        <Modal isOpen onClose={() => setOpened(null)} title={`${opened.group.name} · ${opened.start}–${opened.end}`}>
          <LessonFacts lesson={opened} />
          <ConflictNotes lesson={opened} />
          <p className="mt-3 text-xs text-ink-muted">Расписание в этом интерфейсе только для просмотра. Изменения вносятся в LMS.</p>
        </Modal>
      ) : null}
      {freeRoomsOpen ? (
        <FreeRoomsPanel isOpen onClose={() => setFreeRoomsOpen(false)} initialDate={date} now={now}
          onShowRoom={(roomId, day) => navigate({ pathname: '/schedule/day', search: new URLSearchParams({ ...Object.fromEntries(params), room: String(roomId), date: day }).toString() })} />
      ) : null}
    </div>
  )
}
