import type { BadgeTone } from '@/components/ui/Badge'
import type { LessonAttendanceSummary } from '@/types/academy'
import { ATTENDANCE_SUMMARY_LABELS } from '@/types/attendance'

/**
 * The real, backend-calculated attendance breakdown for one lesson (see
 * services.lesson_summary.attendance_summary on LessonSerializer) — never a
 * second, roster-derived count kept in sync by hand.
 */
export function AttendanceStatsCard({ summary }: { summary: LessonAttendanceSummary }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-5">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm font-medium text-ink-secondary">Посещаемость</p>
        <span className="text-sm text-ink-secondary">{summary.total_students} студентов</span>
      </div>
      <div className="grid grid-cols-4 gap-2 text-center">
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
  }
  return (
    <div className="rounded-lg bg-surface-muted p-3">
      <p className={`text-xl font-semibold ${TONE_TEXT[tone]}`}>{value}</p>
      <p className="text-xs text-ink-secondary">{label}</p>
    </div>
  )
}
