import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { AlertTriangle, DoorOpen } from 'lucide-react'

import { StatusIcon, TrainerDot, lessonLabel, trainerStyle } from '@/features/scheduleBoard/LessonCard'
import { DAY_MINUTES, assignLanes, formatDuration, fromMinutes, hourMarks, place } from '@/features/scheduleBoard/timeGrid'
import type { BoardLesson } from '@/types/schedule'
import { cn } from '@/utils/cn'

/** Taller hours than the LMS board: a one-hour card has room for the time,
 * the full group name, the trainer's full name and the room — nothing is
 * cut with «…»; longer text wraps and the card grows. */
const HOUR_PX = 96
const PX_PER_MIN = HOUR_PX / 60
const GRID_HEIGHT = DAY_MINUTES * PX_PER_MIN
/** Width one lesson needs side by side with another one. */
const LANE_PX = 200

export interface SiteColumn {
  key: string
  header: ReactNode
  lessons: BoardLesson[]
  highlighted?: boolean
  showNow?: boolean
}

/** One lesson: every field in full, wrapped. Read only — a click opens details. */
export function FullLessonCard({ lesson, onOpen, style, className }: {
  lesson: BoardLesson
  onOpen: (lesson: BoardLesson) => void
  style?: React.CSSProperties
  className?: string
}) {
  return (
    <button
      type="button"
      onClick={() => onOpen(lesson)}
      aria-label={lessonLabel(lesson)}
      data-lesson-id={lesson.id}
      className={cn(
        'flex flex-col gap-0.5 overflow-visible rounded-md border border-l-4 border-black/5 px-2 py-1.5 text-left text-ink shadow-xs',
        'break-words hover:z-30 hover:shadow-md focus-visible:z-30 focus-visible:outline-2 focus-visible:outline-brand-500',
        lesson.status === 'cancelled' && 'opacity-60',
        lesson.conflicts.length > 0 && 'ring-2 ring-danger/70',
        className,
      )}
      style={{ ...trainerStyle(lesson.teacher?.color, lesson.status), ...style }}
    >
      <span className="flex flex-wrap items-center gap-x-1 text-xs font-semibold tabular-nums text-ink-secondary">
        {lesson.conflicts.length ? <AlertTriangle className="size-3.5 shrink-0 text-danger" aria-hidden /> : null}
        <span className="whitespace-nowrap">{lesson.start}–{lesson.end}</span>
        <span className="whitespace-nowrap font-normal text-ink-muted">{formatDuration(lesson.duration_minutes)}</span>
        <span className="ml-auto"><StatusIcon status={lesson.status} /></span>
      </span>
      <span className={cn('text-sm font-semibold leading-snug', lesson.status === 'cancelled' && 'line-through')}>{lesson.group.name}</span>
      <span className="flex items-start gap-1.5 text-xs leading-snug">
        <TrainerDot color={lesson.teacher?.color} className="mt-1" />
        <span>{lesson.teacher?.name ?? 'Тренер не указан'}</span>
      </span>
      <span className="flex items-start gap-1.5 text-xs leading-snug text-ink-secondary">
        <DoorOpen className="mt-0.5 size-3.5 shrink-0" aria-hidden />
        <span>{lesson.room?.name ?? 'Без кабинета'}</span>
      </span>
    </button>
  )
}

/** The 08:00–24:00 timetable of the site. Columns get as wide as their
 * busiest moment needs (parallel lessons × LANE_PX); the page scrolls
 * sideways instead of squeezing names. */
export function FullGrid({ columns, nowMinutes, onOpen, scrollTo, minColumnPx = 220 }: {
  columns: SiteColumn[]
  nowMinutes: number | null
  onOpen: (lesson: BoardLesson) => void
  scrollTo: number
  minColumnPx?: number
}) {
  const scroller = useRef<HTMLDivElement>(null)
  useEffect(() => {
    scroller.current?.scrollTo?.({ top: Math.max(0, (scrollTo - 8 * 60 - 45) * PX_PER_MIN) })
  }, [scrollTo])

  const laid = columns.map((column) => {
    const lanes = assignLanes(column.lessons)
    const width = Math.max(minColumnPx, Math.max(1, ...lanes.map((l) => l.lanes)) * LANE_PX)
    return { column, lanes, width }
  })
  const nowTop = nowMinutes !== null && nowMinutes >= 8 * 60 && nowMinutes <= 24 * 60 ? (nowMinutes - 8 * 60) * PX_PER_MIN : null
  const template = `3.5rem ${laid.map(({ width }) => `minmax(${width}px, 1fr)`).join(' ')}`

  return (
    <div ref={scroller} className="card relative max-h-[calc(100dvh-15rem)] min-h-[420px] overflow-auto" data-testid="site-grid">
      <div className="grid" style={{ gridTemplateColumns: template }}>
        <div className="sticky top-0 left-0 z-40 border-b border-border bg-surface" />
        {laid.map(({ column }) => (
          <div key={column.key} className={cn('sticky top-0 z-30 border-b border-l border-border bg-surface px-2 py-2', column.highlighted && 'bg-brand-50')}>
            {column.header}
          </div>
        ))}

        <div className="sticky left-0 z-20 bg-surface" style={{ height: GRID_HEIGHT }} aria-hidden>
          {hourMarks().map((mark, index, all) => (
            <span key={mark} className="absolute right-1.5 -translate-y-1/2 text-xs font-medium tabular-nums text-ink-muted"
              style={{ top: index * HOUR_PX + (index === 0 ? 8 : index === all.length - 1 ? -8 : 0) }}>
              {mark}
            </span>
          ))}
          {nowTop !== null ? (
            <span className="absolute right-0.5 z-10 -translate-y-1/2 rounded bg-danger px-1 text-2xs font-semibold text-white tabular-nums" style={{ top: nowTop }}>
              {fromMinutes(nowMinutes as number)}
            </span>
          ) : null}
        </div>

        {laid.map(({ column, lanes }) => (
          <div key={column.key} className={cn('relative border-l border-border', column.highlighted && 'bg-brand-50/30')}
            style={{
              height: GRID_HEIGHT,
              backgroundImage: `repeating-linear-gradient(to bottom, var(--color-border) 0 1px, transparent 1px ${HOUR_PX / 2}px, color-mix(in srgb, var(--color-border) 45%, transparent) ${HOUR_PX / 2}px ${HOUR_PX / 2 + 1}px, transparent ${HOUR_PX / 2 + 1}px ${HOUR_PX}px)`,
            }}>
            {lanes.map(({ item, lane, lanes: count }) => {
              const { top, height } = place(item.start, item.end)
              return (
                <FullLessonCard
                  key={item.id}
                  lesson={item}
                  onOpen={onOpen}
                  className="absolute"
                  style={{
                    top: top * PX_PER_MIN + 1,
                    minHeight: Math.max(height * PX_PER_MIN - 2, 24),
                    left: `calc(${(lane / count) * 100}% + 2px)`,
                    width: `calc(${100 / count}% - 4px)`,
                  }}
                />
              )
            })}
            {column.showNow && nowTop !== null ? (
              <div className="pointer-events-none absolute inset-x-0 z-10 h-0.5 bg-danger" style={{ top: nowTop }} aria-hidden>
                <span className="absolute -top-1 -left-1 size-2.5 rounded-full bg-danger" />
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  )
}

/**
 * The week as an hour × day table (08:00–24:00): each lesson sits in the row
 * of the hour it starts in, rows grow with their content — every name stays
 * whole and nothing overlaps, however many groups run in parallel. Days
 * keep a readable width; on a narrow screen the table scrolls sideways.
 */
export function WeekTable({ days, lessons, onOpen, nowDate, nowMinutes, onDay }: {
  days: { key: string; header: ReactNode; highlighted?: boolean }[]
  lessons: BoardLesson[]
  onOpen: (lesson: BoardLesson) => void
  nowDate: string | null
  nowMinutes: number | null
  onDay?: (day: string) => void
}) {
  const hours = Array.from({ length: 16 }, (_, i) => 8 + i)
  const cell = new Map<string, BoardLesson[]>()
  const early: BoardLesson[] = []
  for (const lesson of lessons) {
    const hour = Math.floor(Number(lesson.start.slice(0, 2)))
    if (hour < 8) early.push(lesson)
    const key = `${lesson.date}|${Math.max(8, Math.min(23, hour))}`
    cell.set(key, [...(cell.get(key) ?? []), lesson])
  }
  const currentHour = nowMinutes !== null ? Math.floor(nowMinutes / 60) : null
  return (
    <div className="card max-h-[calc(100dvh-15rem)] min-h-[420px] overflow-auto" data-testid="site-week">
      <table className="w-full min-w-[1100px] table-fixed border-collapse text-sm">
        <colgroup>
          <col className="w-14" />
          {days.map((day) => <col key={day.key} />)}
        </colgroup>
        <thead>
          <tr>
            <th className="sticky top-0 left-0 z-30 border-b border-border bg-surface" />
            {days.map((day) => (
              <th key={day.key} className={cn('sticky top-0 z-20 border-b border-l border-border bg-surface px-2 py-2 text-left font-normal', day.highlighted && 'bg-brand-50')}>
                {onDay ? <span className="block">{day.header}</span> : day.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {hours.map((hour) => (
            <tr key={hour} className="border-b border-border last:border-0">
              <th scope="row" className={cn('sticky left-0 z-10 bg-surface px-1.5 py-1.5 text-right align-top text-xs font-medium tabular-nums',
                currentHour === hour ? 'text-danger' : 'text-ink-muted')}>
                {String(hour).padStart(2, '0')}:00
              </th>
              {days.map((day) => {
                const items = (cell.get(`${day.key}|${hour}`) ?? []).sort((a, b) => a.start.localeCompare(b.start))
                const isNow = nowDate === day.key && currentHour === hour
                return (
                  <td key={day.key} className={cn('border-l border-border p-1 align-top', day.highlighted && 'bg-brand-50/30', isNow && 'bg-danger-soft/40')}>
                    {items.length ? (
                      <div className="space-y-1">
                        {items.map((lesson) => <FullLessonCard key={lesson.id} lesson={lesson} onOpen={onOpen} className="w-full" />)}
                      </div>
                    ) : <div className="h-6" aria-hidden />}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {early.length ? <p className="px-3 py-2 text-xs text-ink-muted">Занятия до 08:00 показаны в строке 08:00.</p> : null}
    </div>
  )
}
