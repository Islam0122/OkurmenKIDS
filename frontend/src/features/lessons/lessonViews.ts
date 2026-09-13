import { addDays, endOfWeek, format, isToday, isTomorrow, parseISO, startOfWeek } from 'date-fns'
import { ru } from 'date-fns/locale'

import type { Lesson } from '@/types/academy'
import { formatDate } from '@/utils/format'

/**
 * Time-based tabs for "Мои занятия" — a Trainer opens this page to answer
 * "what do I teach today/tomorrow/this week", not to browse every Lesson
 * ever generated. "Все уроки" is the only tab that shows a full, paginated
 * history; every other tab is a bounded, real-data slice of it.
 */
export type LessonView = 'today' | 'tomorrow' | 'week' | 'next_week' | 'upcoming' | 'all' | 'completed' | 'cancelled'

export const DEFAULT_LESSON_VIEW: LessonView = 'today'

export const LESSON_VIEW_TABS: { key: LessonView; label: string }[] = [
  { key: 'today', label: 'Сегодня' },
  { key: 'tomorrow', label: 'Завтра' },
  { key: 'week', label: 'Эта неделя' },
  { key: 'next_week', label: 'Следующая неделя' },
  { key: 'upcoming', label: 'Предстоящие' },
  { key: 'all', label: 'Все уроки' },
  { key: 'completed', label: 'Завершённые' },
  { key: 'cancelled', label: 'Отменённые' },
]

export function isLessonView(value: string | null): value is LessonView {
  return value !== null && LESSON_VIEW_TABS.some((tab) => tab.key === value)
}

/** Local calendar date as `YYYY-MM-DD` — matches `useDashboardData.todayISO`,
 * duplicated here to avoid a cross-feature import for one helper. */
export function isoDate(date: Date): string {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 10)
}

export function todayISO(): string {
  return isoDate(new Date())
}

export function tomorrowISO(): string {
  return isoDate(addDays(new Date(), 1))
}

export function addDaysISO(iso: string, amount: number): string {
  return isoDate(addDays(parseISO(iso), amount))
}

export interface DateRange {
  from: string
  to: string
}

export function thisWeekRange(): DateRange {
  const now = new Date()
  return { from: isoDate(startOfWeek(now, { weekStartsOn: 1 })), to: isoDate(endOfWeek(now, { weekStartsOn: 1 })) }
}

export function nextWeekRange(): DateRange {
  const nextWeekAnchor = addDays(new Date(), 7)
  return {
    from: isoDate(startOfWeek(nextWeekAnchor, { weekStartsOn: 1 })),
    to: isoDate(endOfWeek(nextWeekAnchor, { weekStartsOn: 1 })),
  }
}

/** A generous-but-bounded window for "Предстоящие" — real lessons only,
 * never an unbounded fetch (see `fetchAllPages`'s own contract). */
export function upcomingWindow(): DateRange {
  return { from: todayISO(), to: isoDate(addDays(new Date(), 60)) }
}

/** "Сегодня" / "Завтра" / capitalized weekday — the label half of a date section header. */
export function dateSectionLabel(iso: string): string {
  const date = parseISO(iso)
  if (isToday(date)) return 'Сегодня'
  if (isTomorrow(date)) return 'Завтра'
  const weekday = format(date, 'EEEE', { locale: ru })
  return `${weekday.charAt(0).toUpperCase()}${weekday.slice(1)}`
}

/** Full section heading: "Сегодня — 13 сентября" / "Понедельник — 15 сентября". */
export function dateSectionHeading(iso: string): string {
  return `${dateSectionLabel(iso)} — ${formatDate(iso, false)}`
}

export interface LessonDateGroup {
  date: string
  lessons: Lesson[]
}

/** Groups an already-fetched lesson list into ascending, per-day sections —
 * never a flat "09/13 Python, 09/13 Frontend, 09/14 Python…" list. */
export function groupLessonsByDate(lessons: Lesson[]): LessonDateGroup[] {
  const byDate = new Map<string, Lesson[]>()
  for (const lesson of lessons) {
    const bucket = byDate.get(lesson.date)
    if (bucket) bucket.push(lesson)
    else byDate.set(lesson.date, [lesson])
  }
  return Array.from(byDate.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, items]) => ({ date, lessons: [...items].sort((a, b) => a.start_time.localeCompare(b.start_time)) }))
}

/**
 * Whether `lesson` has already happened — its end time is in the past.
 * Deliberately independent of `lesson.status`: a `planned` lesson whose time
 * slot is over still needs attendance/homework done, and a `completed`
 * lesson generated ahead of time could in principle still be in the future.
 */
export function hasLessonPassed(lesson: Lesson, now: Date = new Date()): boolean {
  const today = isoDate(now)
  if (lesson.date !== today) return lesson.date < today
  const [hours, minutes] = lesson.end_time.split(':').map(Number)
  return hours * 60 + minutes <= now.getHours() * 60 + now.getMinutes()
}
