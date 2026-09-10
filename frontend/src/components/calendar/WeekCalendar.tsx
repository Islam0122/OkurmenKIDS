import { LessonCard } from '@/components/academy/LessonCard'
import type { Lesson } from '@/types/academy'
import { cn } from '@/utils/cn'
import { formatDate, formatWeekday } from '@/utils/format'

export interface CalendarDay {
  date: string
  lessons: Lesson[]
  isToday: boolean
}

export interface WeekCalendarProps {
  days: CalendarDay[]
}

export function WeekCalendar({ days }: WeekCalendarProps) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
      {days.map((day) => (
        <div
          key={day.date}
          className={cn(
            'rounded-xl border bg-surface',
            day.isToday ? 'border-brand-500 ring-1 ring-brand-500' : 'border-border',
          )}
        >
          <div className="border-b border-border px-3 py-2.5">
            <p className="text-sm font-semibold capitalize text-ink">{formatWeekday(day.date)}</p>
            <p className="text-xs text-ink-secondary">{formatDate(day.date, false)}</p>
          </div>
          <div className="flex flex-col gap-2 p-2.5">
            {day.lessons.length === 0 ? (
              <p className="px-1 py-2 text-xs text-ink-muted">Занятий нет</p>
            ) : (
              day.lessons.map((lesson) => <LessonCard key={lesson.id} lesson={lesson} compact />)
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
