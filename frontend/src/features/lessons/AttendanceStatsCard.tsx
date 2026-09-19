import { Eye } from 'lucide-react'

import type { BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import type { LessonAttendanceSummary } from '@/types/academy'
import { ATTENDANCE_SUMMARY_LABELS } from '@/types/attendance'

export interface AttendanceStatsCardProps {
  summary: LessonAttendanceSummary
  /** Only a completed/cancelled lesson's card offers a way into the full
   * (read-only) attendance screen — active-lesson callers simply omit this
   * and get the stats alone, same as before. */
  onView?: () => void
}

/**
 * The real, backend-calculated attendance breakdown for one lesson (see
 * services.lesson_summary.attendance_summary on LessonSerializer) — never a
 * second, roster-derived count kept in sync by hand.
 */
export function AttendanceStatsCard({ summary, onView }: AttendanceStatsCardProps) {
  return (
    <div className="rounded-2xl border border-border bg-surface p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <p className="text-sm font-medium text-ink-secondary">Посещаемость</p>
          <span className="text-sm text-ink-secondary">
            {summary.total_students} студентов
            {summary.attendance_rate !== null ? ` · ${summary.attendance_rate}%` : ''}
          </span>
        </div>
        {onView ? (
          <Button variant="secondary" size="sm" leftIcon={<Eye className="size-4" aria-hidden />} onClick={onView}>
            Посмотреть посещаемость
          </Button>
        ) : null}
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <StatBlock label={ATTENDANCE_SUMMARY_LABELS.present} value={summary.present} tone="success" />
        <StatBlock label={ATTENDANCE_SUMMARY_LABELS.absent} value={summary.absent} tone="danger" />
        <StatBlock label={ATTENDANCE_SUMMARY_LABELS.late} value={summary.late} tone="warning" />
        <StatBlock label={ATTENDANCE_SUMMARY_LABELS.excused} value={summary.excused} tone="muted" />
      </div>
    </div>
  )
}

function StatBlock({ label, value, tone }: { label: string; value: number; tone: BadgeTone }) {
  const TONE_TEXT: Record<BadgeTone, string> = {
    success: 'text-brand-700',
    danger: 'text-danger',
    warning: 'text-warning',
    muted: 'text-ink-muted',
    brand: 'text-brand-700',
    info: 'text-info',
  }
  return (
    <div className="rounded-lg bg-surface-muted p-3 text-center">
      <p className={`text-xl font-semibold ${TONE_TEXT[tone]}`}>{value}</p>
      <p className="text-xs text-ink-secondary">{label}</p>
    </div>
  )
}
