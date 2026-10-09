import { useState } from 'react'
import { format, parseISO } from 'date-fns'
import { ru } from 'date-fns/locale'
import { CalendarSearch, CircleCheck, CircleX, Clock } from 'lucide-react'

import { Drawer } from '@/components/ui/Drawer'
import { DatePicker } from '@/components/ui/DatePicker'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { useFreeRooms } from '@/hooks/useSchedule'
import type { RoomAvailabilityRow } from '@/types/schedule'
import { cn } from '@/utils/cn'

import { DAY_END, DAY_START, fromMinutes, toMinutes } from './timeGrid'

const DURATIONS = [
  { value: '60', label: '1 ч' },
  { value: '90', label: '1,5 ч' },
  { value: '120', label: '2 ч' },
]

/** The next half hour inside 08:00–23:00 (or 14:00 for another day). */
export function defaultWindowStart(date: string, now: { date: string; minutes: number } | null): string {
  if (!now || now.date !== date) return '14:00'
  const next = Math.ceil(now.minutes / 30) * 30
  return fromMinutes(Math.min(Math.max(next, DAY_START), DAY_END - 60))
}

/**
 * «Свободные кабинеты»: a date and a time window → every room, free or
 * busy, from the real lessons in the database. A busy room says who holds
 * it, when it frees up and its next free interval; a free room — how long
 * it stays free. «Расписание кабинета» opens that room's day on the board.
 */
export function FreeRoomsPanel({ isOpen, onClose, initialDate, now, onShowRoom }: {
  isOpen: boolean
  onClose: () => void
  initialDate: string
  now: { date: string; minutes: number } | null
  onShowRoom: (roomId: number, date: string) => void
}) {
  const [date, setDate] = useState(initialDate)
  const [start, setStart] = useState(() => defaultWindowStart(initialDate, now))
  const [end, setEnd] = useState(() => fromMinutes(Math.min(toMinutes(defaultWindowStart(initialDate, now)) + 60, DAY_END)))
  const [onlyFree, setOnlyFree] = useState(false)
  const invalid = !start || !end || end <= start
  const { data, isPending, isFetching, isError, refetch } = useFreeRooms({ date, start, end }, isOpen && !invalid)

  const duration = toMinutes(end) - toMinutes(start)
  const setDuration = (minutes: number) => setEnd(fromMinutes(Math.min(toMinutes(start) + minutes, DAY_END)))
  const rows = (data?.rooms ?? []).filter((row) => !onlyFree || row.is_free)

  return (
    <Drawer isOpen={isOpen} onClose={onClose} title="Свободные кабинеты" side="right" size="lg">
      <div className="space-y-3">
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1.4fr_1fr_1fr]">
          <label className="min-w-0 text-xs font-medium text-ink-secondary">Дата
            <DatePicker className="mt-1" value={date} onChange={(e) => setDate(e.target.value)} aria-label="Дата" />
          </label>
          <label className="min-w-0 text-xs font-medium text-ink-secondary">Начало
            <input type="time" step={300} min="08:00" className="form-control mt-1" value={start} aria-label="Время начала"
              onChange={(e) => {
                const next = e.target.value
                if (next && duration > 0) setEnd(fromMinutes(Math.min(toMinutes(next) + duration, DAY_END)))
                setStart(next)
              }} />
          </label>
          <label className="min-w-0 text-xs font-medium text-ink-secondary">Окончание
            <input type="time" step={300} className="form-control mt-1" value={end === '24:00' ? '23:59' : end} aria-label="Время окончания"
              onChange={(e) => setEnd(e.target.value === '23:59' ? '24:00' : e.target.value)} />
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <SegmentedControl aria-label="Длительность" options={DURATIONS} value={String(duration)} onChange={(v) => setDuration(Number(v))} />
          <label className="ml-auto flex items-center gap-2 text-sm text-ink">
            <input type="checkbox" className="size-4 accent-brand-500" checked={onlyFree} onChange={(e) => setOnlyFree(e.target.checked)} />
            Только свободные
          </label>
        </div>

        {invalid ? <p role="alert" className="rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">Время окончания должно быть позже времени начала.</p> : null}
        {!invalid && isPending ? <LoadingState label="Проверяем кабинеты…" /> : null}
        {!invalid && isError ? <ErrorState onRetry={() => void refetch()} /> : null}

        {!invalid && data ? (
          <>
            <p className={cn('flex items-center gap-2 rounded-lg px-3 py-2 text-sm', data.free_count ? 'bg-brand-50 text-brand-700' : 'bg-warning-soft text-warning')} aria-live="polite">
              <CalendarSearch className="size-4 shrink-0" aria-hidden />
              <span>
                <span className="first-letter:uppercase">{format(parseISO(data.date), 'EEEEEE, d MMMM', { locale: ru })}</span>, {data.start}–{data.end}:{' '}
                <strong>свободно {data.free_count} из {data.rooms.length}</strong>
              </span>
              {isFetching ? <span className="ml-auto text-xs text-ink-muted">обновляем…</span> : null}
            </p>
            {rows.length === 0 ? <p className="py-6 text-center text-sm text-ink-muted">{data.rooms.length ? 'Свободных кабинетов на это время нет — посмотрите время освобождения выше.' : 'Активных кабинетов нет.'}</p> : null}
            <ul className="space-y-2">
              {rows.map((row) => <RoomRow key={row.room.id} row={row} onShow={() => { onShowRoom(row.room.id, date); onClose() }} />)}
            </ul>
          </>
        ) : null}
      </div>
    </Drawer>
  )
}

function RoomRow({ row, onShow }: { row: RoomAvailabilityRow; onShow: () => void }) {
  return (
    <li className={cn('rounded-lg border px-3 py-2.5', row.is_free ? 'border-brand-200 bg-brand-50/40' : 'border-border bg-surface')}>
      <div className="flex flex-wrap items-center gap-2">
        {row.is_free ? <CircleCheck className="size-4 text-brand-600" aria-hidden /> : <CircleX className="size-4 text-danger" aria-hidden />}
        <span className="font-semibold text-ink">{row.room.name}</span>
        {row.room.capacity ? <span className="text-xs text-ink-muted">{row.room.capacity} мест</span> : null}
        <span className={cn('rounded-full px-2 py-0.5 text-xs font-medium', row.is_free ? 'bg-brand-500 text-white' : 'bg-danger-soft text-danger')}>
          {row.is_free ? 'Свободен' : 'Занят'}
        </span>
        <button type="button" onClick={onShow} className="ml-auto text-xs font-medium text-brand-700 hover:underline">Расписание кабинета</button>
      </div>
      <div className="mt-1.5 space-y-0.5 text-sm text-ink-secondary">
        {row.is_free && row.free_window ? (
          <p className="flex items-center gap-1.5"><Clock className="size-3.5" aria-hidden />Свободен {row.free_window.start}–{row.free_window.end}</p>
        ) : null}
        {row.conflicting_lessons.map((lesson) => (
          <p key={lesson.id}>Занят: <span className="font-medium text-ink">{lesson.group.name}</span> {lesson.start}–{lesson.end}{lesson.teacher ? ` · ${lesson.teacher.name}` : ''}</p>
        ))}
        {!row.is_free ? (
          <p className="flex flex-wrap items-center gap-x-3 gap-y-0.5">
            {row.free_at ? <span>Освободится в <strong className="text-ink">{row.free_at}</strong></span> : null}
            <span>Ближайшее свободное окно: <strong className="text-ink">{row.next_free ? `${row.next_free.start}–${row.next_free.end}` : 'нет до 24:00'}</strong></span>
          </p>
        ) : null}
        {row.busy.length ? (
          <p className="text-xs text-ink-muted">Занят за день: {row.busy.map((b) => `${b.start}–${b.end}`).join(', ')}</p>
        ) : <p className="text-xs text-ink-muted">В этот день занятий нет</p>}
      </div>
    </li>
  )
}
