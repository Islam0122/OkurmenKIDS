import { User as UserIcon } from 'lucide-react'

import type { MonthlyTeacherReport } from '@/types/monthlyReport'
import { formatMonthYear } from '@/utils/format'

function initialsOf(firstName: string, lastName: string): string {
  const initials = `${firstName.charAt(0)}${lastName.charAt(0)}`.toUpperCase()
  return initials || '?'
}

// Fixed pixel box, never a percentage/hero image — a monthly report's
// photo is a small profile element, not a banner. The wrapper (not the
// <img> itself) owns the size, so nothing outside this file — a global
// `img { height: auto }` reset included — can ever make it grow.
const AVATAR_CLASSES = 'size-[72px] shrink-0 overflow-hidden rounded-xl sm:size-24'

export function ReportHeader({ report }: { report: MonthlyTeacherReport }) {
  const { teacher } = report
  const fullName = `${teacher.user.last_name} ${teacher.user.first_name}`.trim() || teacher.user.username

  return (
    <div className="rounded-xl border border-border bg-surface p-4 sm:p-5">
      <div className="flex items-center gap-4">
        {teacher.image ? (
          <span className={AVATAR_CLASSES}>
            <img src={teacher.image} alt={fullName} className="size-full object-cover" />
          </span>
        ) : (
          <span className={`${AVATAR_CLASSES} flex items-center justify-center bg-brand-50 text-lg font-bold text-brand-700`}>
            {teacher.user.first_name || teacher.user.last_name ? (
              initialsOf(teacher.user.first_name, teacher.user.last_name)
            ) : (
              <UserIcon className="size-6" aria-hidden />
            )}
          </span>
        )}
        <div className="min-w-0">
          <p className="truncate text-base font-semibold text-ink sm:text-lg">{fullName}</p>
          <p className="text-sm text-ink-secondary">{teacher.position || 'Преподаватель'}</p>
          <p className="mt-0.5 text-sm font-semibold text-brand-600">{formatMonthYear(report.year, report.month)}</p>
        </div>
      </div>
    </div>
  )
}
