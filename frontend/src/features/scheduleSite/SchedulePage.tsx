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
import { TrainerDot } from '@/features/scheduleBoard/LessonCard'
import { DAY_END, formatDuration, toMinutes } from '@/features/scheduleBoard/timeGrid'
import { usePublicOptions, usePublicSchedule } from '@/hooks/usePublicSchedule'
import type { PublicLesson } from '@/types/publicSchedule'
import { cn } from '@/utils/cn'

import { FullGrid, FullLessonCard, WeekTable } from './FullGrid'
import type { SiteColumn } from './FullGrid'

export type SiteView = 'day' | 'week'

const LAST_QUERY = 'okurmen.schedule-site.query'
const iso = (date: Date) => format(date, 'yyyy-MM-dd')
export const ACADEMY_TZ = 'Asia/Bishkek'
/** Today's date in the academy's time zone (sv-SE formats as YYYY-MM-DD). */
const academyToday = () => new Date().toLocaleDateString('sv-SE', { timeZone: ACADEMY_TZ })
const key = (value: string | null) => (value && /^[a-z0-9]{1,32}$/.test(value) ? value : null)

/** /schedule → the last view of this tab, or today. */
export function ScheduleIndex() {
  let target = '/schedule/day'
  try {
    target = sessionStorage.getItem(LAST_QUERY) ?? target
  } catch {
    // storage blocked — today
  }
  return <Navigate to={target.startsWith('/schedule/') ? target : '/schedule/day'} replace />
}

/** The server's «now» (project time zone), kept ticking each minute. */
function useServerNow(now: { date: string; time: string } | undefined, receivedAt: number) {
  const [tick, setTick] = useState(() => Date.now())
  useEffect(() => {
    const id = window.setInterval(() => setTick(Date.now()), 60_000)
    return () => window.clearInterval(id)
  }, [])
  return useMemo(() => {
    if (!now) return null
    const minutes = toMinutes(now.time) + Math.max(0, Math.floor((tick - receivedAt) / 60_000))
    return minutes >= 24 * 60 ? null : { date: now.date, minutes }
  }, [now, receivedAt, tick])
}

export function SiteSchedulePage({ view }: { view: SiteView }) {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const location = useLocation()
  const { data: options } = usePublicOptions()
  const rawDate = params.get('date')
  // «Today» is the academy's (the server's, Asia/Bishkek), not the visitor's clock.
  const date = rawDate && isValid(parseISO(rawDate)) ? rawDate : options?.today ?? academyToday()
  const group = key(params.get('group'))
  const trainer = key(params.get('trainer'))
  const room = key(params.get('room'))
  const query = params.get('q') ?? ''
  const [opened, setOpened] = useState<PublicLesson | null>(null)

  // The view's state is its URL: a link opens the same schedule; it survives День / Неделя.
  useEffect(() => {
    try {
      sessionStorage.setItem(LAST_QUERY, `${location.pathname}${location.search}`)
    } catch {
      // ignore
    }
  }, [location.pathname, location.search])

  const set = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    for (const [name, value] of Object.entries(patch)) {
      if (value === null || value === '') next.delete(name)
      else next.set(name, value)
    }
    setParams(next, { replace: true })
  }
  const go = (pathname: string, patch: Record<string, string> = {}) =>
    navigate({ pathname, search: new URLSearchParams({ ...Object.fromEntries(params), ...patch }).toString() })

  const range = useMemo(() => {
    if (view === 'day') return { start: date, end: date }
    const anchor = parseISO(date)
    return { start: iso(startOfWeek(anchor, { weekStartsOn: 1 })), end: iso(endOfWeek(anchor, { weekStartsOn: 1 })) }
  }, [view, date])
  const days = useMemo(() => eachDayOfInterval({ start: parseISO(range.start), end: parseISO(range.end) }).map(iso), [range])

  const { data, isPending, isFetching, isError, error, refetch, dataUpdatedAt } = usePublicSchedule({
    start: range.start, end: range.end, group: group ?? undefined, trainer: trainer ?? undefined, room: room ?? undefined,
  })
  const now = useServerNow(data?.now, dataUpdatedAt)
  const stale = data !== undefined && (data.start !== range.start || data.end !== range.end)
  const showTrainers = options?.show.trainers ?? data?.show.trainers ?? true
  const showRooms = options?.show.rooms ?? data?.show.rooms ?? true
  const lessons = useMemo(() => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean)
    return (data?.lessons ?? []).filter((l) => {
      if (!words.length) return true
      const text = [l.group.name, l.course, l.subject, l.trainer?.name, l.room?.name].filter(Boolean).join(' ').toLowerCase()
      return words.every((w) => text.includes(w))
    })
  }, [data, query])
  const hasFilters = Boolean(group || trainer || room || query)
  const outOfWindow = (error as { response?: { status?: number; data?: { detail?: string } } } | null)?.response

  const columns: SiteColumn[] = useMemo(() => {
    if (view === 'week') {
      return days.map((day) => ({
        key: day,
        header: (
          <button type="button" onClick={() => go('/schedule/day', { date: day })} className="flex w-full items-baseline gap-1.5 text-left hover:text-brand-700" title="Открыть день">
            <span className={cn('text-xs font-semibold uppercase', isToday(parseISO(day)) ? 'text-brand-700' : 'text-ink-secondary')}>
              {format(parseISO(day), 'EEEEEE', { locale: ru })}
            </span>
            <span className={cn('rounded-full px-1.5 text-sm font-semibold', isToday(parseISO(day)) ? 'bg-brand-500 text-white' : 'text-ink')}>{format(parseISO(day), 'd MMM', { locale: ru })}</span>
          </button>
        ),
        lessons: lessons.filter((l) => l.date === day),
        highlighted: now?.date === day,
        showNow: now?.date === day,
      }))
    }
    if (!showRooms) {
      return [{ key: 'all', header: <span className="text-sm font-semibold text-ink">Все занятия</span>, lessons, showNow: now?.date === date }]
    }
    // Day: a column per room that has lessons (or the selected room).
    const used = new Map<string, string>()
    for (const l of lessons) if (l.room) used.set(l.room.key, l.room.name)
    const ordered = (options?.rooms ?? []).filter((r) => used.has(r.key) || r.key === room)
    for (const [k, name] of used) if (!ordered.some((r) => r.key === k)) ordered.push({ key: k, name })
    const result: SiteColumn[] = ordered.map((r) => ({
      key: r.key,
      header: (
        <div className="flex items-center gap-1.5">
          <DoorOpen className="size-4 shrink-0 text-ink-muted" aria-hidden />
          <span className="text-sm font-semibold text-ink">{r.name}</span>
        </div>
      ),
      lessons: lessons.filter((l) => l.room?.key === r.key),
      showNow: now?.date === date,
    }))
    const roomless = lessons.filter((l) => !l.room)
    if (roomless.length || !result.length) {
      result.push({ key: 'no-room', header: <span className="text-sm font-semibold text-ink-secondary">{result.length ? 'Кабинет уточняется' : 'Занятия'}</span>, lessons: roomless, showNow: now?.date === date })
    }
    return result
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, days, lessons, options, now, date, room, showRooms])

  const firstStart = lessons.filter((l) => l.status !== 'cancelled').map((l) => toMinutes(l.start)).sort((a, b) => a - b)[0]
  const scrollTarget = now && days.includes(now.date) ? now.minutes : firstStart ?? 8 * 60
  const title = view === 'day'
    ? format(parseISO(date), 'EEEE, d MMMM yyyy', { locale: ru })
    : `${format(parseISO(range.start), 'd MMM', { locale: ru })} – ${format(parseISO(range.end), 'd MMM yyyy', { locale: ru })}`
  const live = lessons.filter((l) => l.status !== 'cancelled')
  const happeningNow = now ? lessons.filter((l) => l.date === now.date && l.status !== 'cancelled' && toMinutes(l.start) <= now.minutes && now.minutes < (toMinutes(l.end) || DAY_END)).length : 0

  return (
    <div>
      {/* Date navigation */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1">
          <Button variant="secondary" className="w-10 px-0" aria-label={view === 'day' ? 'Предыдущий день' : 'Предыдущая неделя'}
            onClick={() => set({ date: iso(addDays(parseISO(date), view === 'day' ? -1 : -7)) })}><ChevronLeft className="size-4" aria-hidden /></Button>
          <Button variant="secondary" onClick={() => set({ date: null })}>Сегодня</Button>
          <Button variant="secondary" className="w-10 px-0" aria-label={view === 'day' ? 'Следующий день' : 'Следующая неделя'}
            onClick={() => set({ date: iso(addDays(parseISO(date), view === 'day' ? 1 : 7)) })}><ChevronRight className="size-4" aria-hidden /></Button>
        </div>
        <DatePicker aria-label="Дата" className="w-36 sm:w-40" value={date} min={options?.window.first} max={options?.window.last}
          onChange={(e) => e.target.value && set({ date: e.target.value })} />
        <SegmentedControl aria-label="Вид расписания" value={view} onChange={(v) => go(`/schedule/${v}`)}
          options={[{ value: 'day', label: 'День' }, { value: 'week', label: 'Неделя' }]} />
        <h1 className="order-last w-full text-lg font-semibold text-ink first-letter:uppercase lg:order-none lg:w-auto">{title}</h1>
        <span className="ml-auto hidden items-center gap-1 text-xs text-ink-muted md:inline-flex" title="Обновляется автоматически каждую минуту">
          {isFetching ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : <RefreshCw className="size-3.5" aria-hidden />}
          {dataUpdatedAt ? `обновлено ${format(dataUpdatedAt, 'HH:mm')}` : ''}
        </span>
      </div>

      {/* Filters (server side) and group search (over the loaded days) */}
      <div className={cn('mb-3 grid grid-cols-1 gap-2 min-[520px]:grid-cols-2',
        showTrainers && showRooms ? 'lg:grid-cols-[repeat(3,minmax(0,16rem))_minmax(0,18rem)_auto]' : 'lg:grid-cols-[repeat(2,minmax(0,16rem))_minmax(0,18rem)_auto]')}>
        <Select aria-label="Группа" value={group ?? ''} placeholder="Все группы" className={cn(group && 'border-brand-500')}
          onChange={(e) => set({ group: e.target.value || null })}
          options={(options?.groups ?? []).map((g) => ({ value: g.key, label: `${g.name} — ${g.course}` }))} />
        {showTrainers ? (
          <Select aria-label="Тренер" value={trainer ?? ''} placeholder="Все тренеры" className={cn(trainer && 'border-brand-500')}
            onChange={(e) => set({ trainer: e.target.value || null })}
            options={(options?.trainers ?? []).map((t) => ({ value: t.key, label: t.name }))} />
        ) : null}
        {showRooms ? (
          <Select aria-label="Кабинет" value={room ?? ''} placeholder="Все кабинеты" className={cn(room && 'border-brand-500')}
            onChange={(e) => set({ room: e.target.value || null })}
            options={(options?.rooms ?? []).map((r) => ({ value: r.key, label: r.name }))} />
        ) : null}
        <label className="relative block">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-muted" aria-hidden />
          <input type="search" aria-label="Поиск группы" placeholder="Найти группу…" value={query}
            onChange={(e) => set({ q: e.target.value || null })} className="form-control pl-9" />
          {query ? (
            <button type="button" aria-label="Очистить поиск" onClick={() => set({ q: null })} className="absolute top-1/2 right-2 -translate-y-1/2 rounded p-1 text-ink-muted hover:bg-surface-hover">
              <X className="size-4" aria-hidden />
            </button>
          ) : null}
        </label>
        {hasFilters ? (
          <Button variant="ghost" leftIcon={<FilterX className="size-4" aria-hidden />} className="justify-self-start"
            onClick={() => set({ group: null, trainer: null, room: null, q: null })}>Сбросить</Button>
        ) : null}
      </div>

      {data ? (
        <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          <span className="text-ink"><strong className="tabular-nums">{live.length}</strong> занятий{happeningNow ? ` · сейчас идёт: ${happeningNow}` : ''}</span>
          {showTrainers && options?.trainers.length ? (
            <span className="flex flex-wrap items-center gap-1.5" aria-label="Тренеры и их цвета">
              {(options.trainers.filter((t) => lessons.some((l) => l.trainer?.key === t.key))).map((t) => (
                <button key={t.key} type="button" aria-pressed={trainer === t.key} onClick={() => set({ trainer: trainer === t.key ? null : t.key })}
                  className={cn('inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs text-ink',
                    trainer === t.key ? 'border-ink/30 bg-surface-hover font-semibold' : 'border-border bg-surface hover:bg-surface-hover')}>
                  <TrainerDot color={t.color} />{t.name}
                </button>
              ))}
            </span>
          ) : null}
        </div>
      ) : null}

      {isPending ? <LoadingState label="Загружаем расписание…" /> : null}
      {isError && !data ? (
        outOfWindow?.status === 400 && outOfWindow.data?.detail ? (
          <div className="card px-4 py-6 text-center text-sm text-ink-secondary">
            {outOfWindow.data.detail} <button type="button" className="font-medium text-brand-700 underline" onClick={() => set({ date: null })}>К сегодняшнему дню</button>
          </div>
        ) : <ErrorState onRetry={() => void refetch()} />
      ) : null}
      {isError && data ? (
        <p role="alert" className="mb-3 rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning">
          {outOfWindow?.status === 400 && outOfWindow.data?.detail ? outOfWindow.data.detail : 'Не удалось обновить расписание — показаны последние загруженные данные.'}{' '}
          <button type="button" className="font-medium underline" onClick={() => set({ date: null })}>Сегодня</button>
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
              <FullGrid columns={columns} nowMinutes={now && days.includes(now.date) ? now.minutes : null} onOpen={setOpened} scrollTo={scrollTarget} />
            ) : (
              <WeekTable days={columns} lessons={lessons} onOpen={setOpened} nowDate={now?.date ?? null}
                nowMinutes={now && days.includes(now.date) ? now.minutes : null} />
            )}
          </div>
          {/* Phones: a list by day — easy to read with one hand */}
          <div className="space-y-4 md:hidden" data-testid="site-agenda">
            {days.map((day) => {
              const items = lessons.filter((l) => l.date === day)
              if (days.length > 1 && !items.length) return null
              return (
                <section key={day}>
                  <h2 className={cn('mb-1.5 text-sm font-semibold first-letter:uppercase', isToday(parseISO(day)) ? 'text-brand-700' : 'text-ink')}>
                    {format(parseISO(day), 'EEEE, d MMMM', { locale: ru })}
                  </h2>
                  {items.length ? (
                    <div className="space-y-2">{items.map((l) => <FullLessonCard key={l.key} lesson={l} onOpen={setOpened} className="w-full" />)}</div>
                  ) : <p className="text-sm text-ink-muted">Занятий нет</p>}
                </section>
              )
            })}
          </div>
        </div>
      ) : null}

      {opened ? (
        <Modal isOpen onClose={() => setOpened(null)} title={opened.group.name}>
          <dl className="grid grid-cols-2 gap-3 rounded-lg bg-surface-muted p-3 text-sm">
            <div><dt className="field-label">Дата</dt><dd className="font-medium text-ink first-letter:uppercase">{format(parseISO(opened.date), 'EEEE, d MMMM', { locale: ru })}</dd></div>
            <div><dt className="field-label">Время</dt><dd className="font-medium text-ink tabular-nums">{opened.start}–{opened.end} · {formatDuration(opened.duration_minutes)}</dd></div>
            <div><dt className="field-label">Курс</dt><dd className="font-medium text-ink">{opened.course}</dd></div>
            {opened.subject ? <div><dt className="field-label">Предмет</dt><dd className="font-medium text-ink">{opened.subject}</dd></div> : null}
            {opened.trainer ? <div><dt className="field-label">Тренер</dt><dd className="flex items-center gap-1.5 font-medium text-ink"><TrainerDot color={opened.trainer.color} />{opened.trainer.name}</dd></div> : null}
            {opened.room !== undefined ? <div><dt className="field-label">Кабинет</dt><dd className="font-medium text-ink">{opened.room?.name ?? 'Уточняется'}</dd></div> : null}
            <div><dt className="field-label">Статус</dt><dd className="font-medium text-ink">{opened.status_label}{opened.rescheduled ? ' · время изменено' : ''}</dd></div>
          </dl>
        </Modal>
      ) : null}
    </div>
  )
}
