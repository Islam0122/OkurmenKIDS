import { format, isToday, parseISO } from 'date-fns'
import { ru } from 'date-fns/locale'
import { AlertTriangle, DoorOpen } from 'lucide-react'

import type { BoardLesson } from '@/types/schedule'
import { cn } from '@/utils/cn'

import { StatusIcon, TrainerDot, lessonLabel, trainerStyle } from './LessonCard'
import { formatDuration, toMinutes } from './timeGrid'

/**
 * The phone layout: lessons as a list by day and time — every field
 * readable without a timetable to squeeze into 360px. The current lesson is
 * marked, past ones are muted.
 */
export function AgendaList({ lessons, days, now, onOpen }: {
  lessons: BoardLesson[]
  days: string[]
  now: { date: string; minutes: number } | null
  onOpen: (lesson: BoardLesson) => void
}) {
  return (
    <div className="space-y-3" data-testid="agenda">
      {days.map((day) => {
        const items = lessons.filter((lesson) => lesson.date === day)
        if (days.length > 1 && items.length === 0) return null
        return (
          <section key={day} className="card overflow-hidden">
            <h3 className={cn('border-b border-border bg-surface-muted px-3 py-2 text-sm font-semibold first-letter:uppercase', isToday(parseISO(day)) ? 'text-brand-700' : 'text-ink')}>
              {format(parseISO(day), 'EEEE, d MMMM', { locale: ru })}
              <span className="ml-2 font-normal text-ink-secondary">{items.length ? `${items.length} зан.` : ''}</span>
            </h3>
            {items.length === 0 ? <p className="px-3 py-4 text-sm text-ink-muted">Занятий нет</p> : null}
            <ul className="divide-y divide-border">
              {items.map((lesson) => {
                const current = now?.date === lesson.date && toMinutes(lesson.start) <= now.minutes && now.minutes < (toMinutes(lesson.end) || 1440)
                const past = now !== null && (lesson.date < now.date || (lesson.date === now.date && (toMinutes(lesson.end) || 1440) <= now.minutes))
                return (
                  <li key={lesson.id}>
                    <button type="button" onClick={() => onOpen(lesson)} aria-label={lessonLabel(lesson)}
                      className={cn('flex w-full gap-3 border-l-4 px-3 py-2.5 text-left hover:brightness-[0.98]', past && lesson.status !== 'in_progress' && 'opacity-70')}
                      style={trainerStyle(lesson.teacher?.color, lesson.status)}>
                      <span className="w-14 shrink-0 tabular-nums">
                        <span className="block text-sm font-semibold text-ink">{lesson.start}</span>
                        <span className="block text-xs text-ink-secondary">{lesson.end}</span>
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-1.5">
                          {lesson.conflicts.length ? <AlertTriangle className="size-4 shrink-0 text-danger" aria-hidden /> : null}
                          <span className={cn('truncate font-semibold text-ink', lesson.status === 'cancelled' && 'line-through')}>{lesson.group.name}</span>
                          {current ? <span className="shrink-0 rounded-full bg-danger px-1.5 text-2xs font-semibold text-white">сейчас</span> : null}
                          <span className="ml-auto"><StatusIcon status={lesson.status} /></span>
                        </span>
                        <span className="mt-0.5 flex items-center gap-1.5 text-xs text-ink-secondary">
                          <TrainerDot color={lesson.teacher?.color} />
                          <span className="truncate">{lesson.teacher?.name ?? 'Тренер не указан'}</span>
                        </span>
                        <span className="mt-0.5 flex items-center gap-1.5 text-xs text-ink-muted">
                          <DoorOpen className="size-3.5 shrink-0" aria-hidden />
                          <span className="truncate">{lesson.room?.name ?? 'Без кабинета'} · {formatDuration(lesson.duration_minutes)}{lesson.status !== 'scheduled' ? ` · ${lesson.status_display}` : ''}</span>
                        </span>
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
          </section>
        )
      })}
    </div>
  )
}
