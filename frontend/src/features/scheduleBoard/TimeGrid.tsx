import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'

import type { BoardLesson } from '@/types/schedule'
import { cn } from '@/utils/cn'

import { LessonCard } from './LessonCard'
import { DAY_MINUTES, assignLanes, fromMinutes, hourMarks, place, slotAt, toMinutes } from './timeGrid'

/** Pixels per hour: 16 working hours fit one laptop screen with a little scroll. */
const HOUR_PX = 52
const PX_PER_MIN = HOUR_PX / 60
const GRID_HEIGHT = DAY_MINUTES * PX_PER_MIN

export interface GridColumn {
  key: string
  header: ReactNode
  lessons: BoardLesson[]
  highlighted?: boolean
  /** Shows the current-time line in this column. */
  showNow?: boolean
  /** Click on an empty spot: the 30-minute slot's start («HH:MM»). */
  onEmptyClick?: (start: string) => void
  /** Click on a summary of too many parallel lessons (see `maxLanes`). */
  onCrowdClick?: (start: string) => void
}

/**
 * The 08:00–24:00 timetable: an hour ruler on the left, one column per room
 * (day view) or per day (week view). Lessons are placed by their real start
 * and end, overlapping ones share the column in lanes. The ruler and the
 * column headers stay put while the grid scrolls.
 */
export function TimeGrid({
  columns,
  nowMinutes,
  onOpen,
  scrollTo,
  showRoom = true,
  minColumnWidth = 132,
  maxLanes = Infinity,
}: {
  columns: GridColumn[]
  nowMinutes: number | null
  onOpen: (lesson: BoardLesson) => void
  /** Minutes since midnight to scroll to on first render. */
  scrollTo: number
  showRoom?: boolean
  minColumnWidth?: number
  /** More parallel lessons than this in one column become one summary block. */
  maxLanes?: number
}) {
  const scroller = useRef<HTMLDivElement>(null)
  const marks = hourMarks()

  useEffect(() => {
    const target = Math.max(0, (scrollTo - 8 * 60 - 45) * PX_PER_MIN)
    scroller.current?.scrollTo?.({ top: target })
  }, [scrollTo])

  const nowTop = nowMinutes !== null && nowMinutes >= 8 * 60 && nowMinutes <= 24 * 60 ? (nowMinutes - 8 * 60) * PX_PER_MIN : null

  return (
    <div ref={scroller} className="card relative max-h-[min(72dvh,860px)] overflow-auto" data-testid="time-grid">
      <div className="grid" style={{ gridTemplateColumns: `3.25rem repeat(${columns.length}, minmax(${minColumnWidth}px, 1fr))` }}>
        {/* Header row */}
        <div className="sticky top-0 left-0 z-30 border-b border-border bg-surface" />
        {columns.map((column) => (
          <div
            key={column.key}
            className={cn('sticky top-0 z-20 min-w-0 border-b border-l border-border bg-surface px-2 py-2', column.highlighted && 'bg-brand-50')}
          >
            {column.header}
          </div>
        ))}

        {/* Hour ruler */}
        <div className="sticky left-0 z-10 bg-surface" style={{ height: GRID_HEIGHT }} aria-hidden>
          {marks.map((mark, index) => (
            <span
              key={mark}
              className="absolute right-1.5 -translate-y-1/2 text-2xs font-medium tabular-nums text-ink-muted"
              style={{ top: index * HOUR_PX + (index === 0 ? 7 : index === marks.length - 1 ? -7 : 0) }}
            >
              {mark}
            </span>
          ))}
          {nowTop !== null ? (
            <span className="absolute right-0.5 z-10 -translate-y-1/2 rounded bg-danger px-1 text-2xs font-semibold text-white tabular-nums" style={{ top: nowTop }}>
              {fromMinutes(nowMinutes as number)}
            </span>
          ) : null}
        </div>

        {columns.map((column) => (
          <div
            key={column.key}
            role={column.onEmptyClick ? 'button' : undefined}
            tabIndex={-1}
            aria-label={column.onEmptyClick ? 'Свободное время — нажмите, чтобы добавить занятие' : undefined}
            onClick={
              column.onEmptyClick
                ? (event) => {
                    const rect = event.currentTarget.getBoundingClientRect()
                    column.onEmptyClick?.(fromMinutes(slotAt((event.clientY - rect.top) / PX_PER_MIN)))
                  }
                : undefined
            }
            className={cn(
              'relative min-w-0 border-l border-border',
              column.highlighted && 'bg-brand-50/30',
              column.onEmptyClick && 'cursor-copy',
            )}
            style={{
              height: GRID_HEIGHT,
              backgroundImage: `repeating-linear-gradient(to bottom, var(--color-border) 0 1px, transparent 1px ${HOUR_PX / 2}px, color-mix(in srgb, var(--color-border) 45%, transparent) ${HOUR_PX / 2}px ${HOUR_PX / 2 + 1}px, transparent ${HOUR_PX / 2 + 1}px ${HOUR_PX}px)`,
            }}
          >
            {renderColumn(column, onOpen, showRoom, maxLanes)}
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

function renderColumn(column: GridColumn, onOpen: (lesson: BoardLesson) => void, showRoom: boolean, maxLanes: number) {
  const laned = assignLanes(column.lessons)
  const crowded = new Map<number, BoardLesson[]>()
  for (const entry of laned) {
    if (entry.lanes > maxLanes) crowded.set(entry.cluster, [...(crowded.get(entry.cluster) ?? []), entry.item])
  }
  const cards = laned.filter((entry) => entry.lanes <= maxLanes).map(({ item, lane, lanes }) => {
    const { top, height } = place(item.start, item.end)
    const px = height * PX_PER_MIN
    return (
      <LessonCard
        key={item.id}
        lesson={item}
        onOpen={onOpen}
        showRoom={showRoom}
        density={px < 34 ? 'tiny' : px < 70 ? 'compact' : 'full'}
        className="absolute"
        style={{
          top: top * PX_PER_MIN + 1,
          height: Math.max(px - 2, 18),
          left: `calc(${(lane / lanes) * 100}% + 2px)`,
          width: `calc(${100 / lanes}% - 4px)`,
        }}
      />
    )
  })
  // Too many lessons at once for the column's width: one block that says
  // how many and whose (trainer colors), opening the day view on click.
  const summaries = [...crowded.entries()].map(([key, items]) => {
    const start = Math.min(...items.map((l) => toMinutes(l.start)))
    const end = Math.max(...items.map((l) => toMinutes(l.end) || 24 * 60))
    const { top, height } = place(fromMinutes(start), fromMinutes(end))
    const conflicts = items.filter((l) => l.conflicts.length).length
    const colors = [...new Set(items.map((l) => l.teacher?.color ?? '#94A3B8'))]
    return (
      <button
        key={`crowd-${key}`}
        type="button"
        onClick={(event) => {
          event.stopPropagation()
          column.onCrowdClick?.(fromMinutes(start))
        }}
        title={items.map((l) => `${l.start}–${l.end} ${l.group.name} · ${l.teacher?.name ?? '—'}${l.room ? ` · ${l.room.name}` : ''}`).join('\n')}
        aria-label={`${items.length} занятий одновременно, ${fromMinutes(start)}–${fromMinutes(end)}. Открыть день`}
        className="absolute inset-x-0.5 z-[5] flex flex-col overflow-hidden rounded-md border border-border-strong bg-surface-muted px-1.5 py-1 text-left shadow-xs hover:z-20 hover:bg-surface-hover"
        style={{ top: top * PX_PER_MIN + 1, height: Math.max(height * PX_PER_MIN - 2, 18) }}
      >
        <span className="text-2xs font-semibold tabular-nums text-ink-secondary">{fromMinutes(start)}–{fromMinutes(end)}</span>
        <span className="text-sm font-semibold text-ink">{items.length} занятий</span>
        <span className="mt-0.5 flex flex-wrap gap-0.5">
          {colors.map((color) => <span key={color} className="size-2 rounded-full" style={{ backgroundColor: color }} aria-hidden />)}
        </span>
        {conflicts ? <span className="mt-auto text-2xs font-medium text-danger">конфликтов: {conflicts}</span> : null}
      </button>
    )
  })
  return [...summaries, ...cards]
}
