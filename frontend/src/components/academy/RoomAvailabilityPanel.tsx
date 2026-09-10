import { useState } from 'react'
import { format } from 'date-fns'

import { Badge } from '@/components/ui/Badge'
import { DatePicker } from '@/components/ui/DatePicker'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { useRoomAvailability } from '@/hooks/useRooms'
import { formatTimeRange } from '@/utils/format'

export interface RoomAvailabilityPanelProps {
  /** Pre-fills the query from the page that opened this panel (e.g. the currently viewed schedule day). */
  defaultDate?: string
}

/** "Кто свободен, кто занят" — a Trainer/Admin picks a date + time window and
 * sees which Rooms are free right now vs. already booked (and by which
 * group), before trying to schedule something into one. */
export function RoomAvailabilityPanel({ defaultDate }: RoomAvailabilityPanelProps) {
  const [date, setDate] = useState(defaultDate ?? format(new Date(), 'yyyy-MM-dd'))
  const [startTime, setStartTime] = useState('09:00')
  const [endTime, setEndTime] = useState('10:00')

  const { data, isPending, isError, refetch } = useRoomAvailability({
    date,
    start_time: startTime,
    end_time: endTime,
  })

  const timeError = startTime && endTime && endTime <= startTime

  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <h3 className="text-sm font-semibold text-ink">Свободные аудитории</h3>
      <p className="mt-0.5 text-xs text-ink-secondary">Выберите дату и время, чтобы увидеть занятые и свободные аудитории.</p>

      <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
        <DatePicker aria-label="Дата" value={date} onChange={(event) => setDate(event.target.value)} />
        <input
          type="time"
          aria-label="Время начала"
          value={startTime}
          onChange={(event) => setStartTime(event.target.value)}
          className="h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm text-ink focus-visible:border-brand-500"
        />
        <input
          type="time"
          aria-label="Время окончания"
          value={endTime}
          onChange={(event) => setEndTime(event.target.value)}
          className="h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm text-ink focus-visible:border-brand-500"
        />
      </div>

      {timeError ? <p className="mt-2 text-xs text-danger">Время окончания должно быть позже времени начала.</p> : null}

      {!timeError && isPending ? <div className="mt-4"><LoadingState label="Проверяем аудитории…" /></div> : null}
      {!timeError && isError ? <div className="mt-4"><ErrorState onRetry={() => void refetch()} /></div> : null}

      {!timeError && data ? (
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-secondary">
              🟢 Свободные
            </h4>
            {data.available.length === 0 ? (
              <p className="text-sm text-ink-muted">Нет свободных аудиторий.</p>
            ) : (
              <ul className="space-y-1.5">
                {data.available.map((room) => (
                  <li key={room.id}>
                    <Badge tone="success">{room.name}</Badge>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div>
            <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-secondary">
              🔴 Занятые
            </h4>
            {data.occupied.length === 0 ? (
              <p className="text-sm text-ink-muted">Все аудитории свободны.</p>
            ) : (
              <ul className="space-y-1.5">
                {data.occupied.map((row) => (
                  <li key={row.lesson} className="text-sm text-ink">
                    <span className="font-medium">{row.room_name}</span>
                    {row.group_name ? <span className="text-ink-secondary"> — {row.group_name}</span> : null}
                    <span className="block text-xs text-ink-muted">{formatTimeRange(row.start_time, row.end_time)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ) : null}
    </div>
  )
}
