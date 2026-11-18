import { useEffect, useState } from 'react'
import { BookOpen, Code2, Languages, Sparkles } from 'lucide-react'

import type { PortalLesson } from '@/types/studentPortal'

import { isoDate } from '../ui'

/**
 * Pure helpers of the student schedule (/student/schedule). Everything here
 * is derived from the fields /api/v1/portal/students/:id/schedule/ returns
 * (apps.portal.services.data.lesson_row) — nothing is invented:
 *
 * - the five UI statuses map the lesson's own status plus the student's
 *   attendance mark: «Пропущено» is a lesson the trainer marked absent or
 *   excused (the portal's attendance rules count both as missed);
 * - the subject accent is read off the subject's name (IT / English /
 *   Soft Skills — the same split apps.academic_progress.numbering uses).
 */

export type View = 'week' | 'month'
export type UiStatus = 'scheduled' | 'in_progress' | 'completed' | 'missed' | 'cancelled'

export function uiStatus(lesson: PortalLesson): UiStatus {
  if (lesson.status === 'cancelled') return 'cancelled'
  if (lesson.attendance === 'absent' || lesson.attendance === 'excused') return 'missed'
  return lesson.status
}

export type SubjectKind = 'it' | 'english' | 'soft'

export function subjectKind(lesson: PortalLesson): SubjectKind {
  const name = (lesson.subject?.name ?? '').toLowerCase()
  if (/english|англ|англис/.test(name)) return 'english'
  if (/soft|софт/.test(name)) return 'soft'
  return 'it'
}

/** Accent per subject — tailwind classes only (tokens in index.css / default palette). */
export const SUBJECT_TONE: Record<SubjectKind, { bar: string; chip: string; dot: string; soft: string; icon: typeof Code2 }> = {
  it: { bar: 'bg-brand-500', chip: 'bg-brand-50 text-brand-700', dot: 'bg-brand-500', soft: 'bg-brand-50/70 text-brand-700', icon: Code2 },
  english: { bar: 'bg-sky-500', chip: 'bg-sky-50 text-sky-700', dot: 'bg-sky-500', soft: 'bg-sky-50 text-sky-700', icon: Languages },
  soft: { bar: 'bg-violet-500', chip: 'bg-violet-50 text-violet-700', dot: 'bg-violet-500', soft: 'bg-violet-50 text-violet-700', icon: Sparkles },
}
export const NO_SUBJECT_ICON = BookOpen

export function mondayOf(d: Date) {
  const copy = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  copy.setDate(copy.getDate() - ((copy.getDay() + 6) % 7))
  return copy
}

export function addDays(d: Date, n: number) {
  const copy = new Date(d)
  copy.setDate(copy.getDate() + n)
  return copy
}

/** Week: Monday → Sunday. Month: the grid — Monday of the first week → Sunday of the last. */
export function range(view: View, anchor: Date): [Date, Date] {
  if (view === 'week') {
    const start = mondayOf(anchor)
    return [start, addDays(start, 6)]
  }
  const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1)
  const last = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0)
  return [mondayOf(first), addDays(mondayOf(last), 6)]
}

export function daysBetween(start: Date, end: Date): Date[] {
  const n = Math.round((end.getTime() - start.getTime()) / 86_400_000) + 1
  return Array.from({ length: n }, (_, i) => addDays(start, i))
}

export function minutesOf(hm: string | null | undefined): number | null {
  if (!hm) return null
  const [h, m] = hm.split(':').map(Number)
  return Number.isFinite(h) && Number.isFinite(m) ? h * 60 + m : null
}

export function durationMin(lesson: PortalLesson): number | null {
  const s = minutesOf(lesson.start)
  const e = minutesOf(lesson.end)
  return s !== null && e !== null && e > s ? e - s : null
}

export function byStart(a: PortalLesson, b: PortalLesson) {
  return a.date.localeCompare(b.date) || (a.start ?? '').localeCompare(b.start ?? '')
}

export function groupByDay(lessons: PortalLesson[]) {
  const map = new Map<string, PortalLesson[]>()
  for (const lesson of [...lessons].sort(byStart)) map.set(lesson.date, [...(map.get(lesson.date) ?? []), lesson])
  return map
}

export interface ScheduleStats {
  /** Lessons that take place (not cancelled). */
  total: number
  completed: number
  upcoming: number
  missed: number
  cancelled: number
}

/** Counts over the lessons the API returned for the period (the month grid is trimmed to the month itself). */
export function stats(lessons: PortalLesson[]): ScheduleStats {
  const s: ScheduleStats = { total: 0, completed: 0, upcoming: 0, missed: 0, cancelled: 0 }
  for (const lesson of lessons) {
    if (lesson.status === 'cancelled') { s.cancelled += 1; continue }
    s.total += 1
    if (lesson.status === 'completed') s.completed += 1
    else s.upcoming += 1
    if (lesson.attendance === 'absent' || lesson.attendance === 'excused') s.missed += 1
  }
  return s
}

export function pct(part: number, whole: number) {
  return whole > 0 ? Math.round((part / whole) * 100) : 0
}

/** The clock, refreshed every `ms` (for the «now» line and «через N мин»). */
export function useNow(ms = 60_000) {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), ms)
    return () => window.clearInterval(id)
  }, [ms])
  return now
}

export function nowMinutes(now: Date) {
  return now.getHours() * 60 + now.getMinutes()
}

export const todayIso = () => isoDate(new Date())
