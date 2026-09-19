import { User as UserIcon } from 'lucide-react'

import type { MonthlyTeacherReport } from '@/types/monthlyReport'
import { formatMonthYear } from '@/utils/format'

function initialsOf(firstName: string, lastName: string): string {
  const initials = `${firstName.charAt(0)}${lastName.charAt(0)}`.toUpperCase()
  return initials || '?'
}

export function ReportHeader({ report }: { report: MonthlyTeacherReport }) {
  const { teacher } = report
  const fullName = `${teacher.user.last_name} ${teacher.user.first_name}`.trim() || teacher.user.username

  const quickStats = [
    { label: 'Занятия', value: report.stats.lessons_completed },
    { label: 'Студенты', value: report.stats.students_count },
    { label: 'Группы', value: report.stats.groups_count },
  ]

  return (
    <div className="rounded-xl border border-border bg-surface p-5 sm:p-6">
      <p className="text-xs font-bold uppercase tracking-wide text-brand-600">OkurmenKIDS</p>

      <div className="mt-4 flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-4">
          {teacher.image ? (
            <img src={teacher.image} alt={fullName} className="size-16 shrink-0 rounded-full object-cover" />
          ) : (
            <span className="flex size-16 shrink-0 items-center justify-center rounded-full bg-brand-50 text-lg font-bold text-brand-700">
              {teacher.user.first_name || teacher.user.last_name ? (
                initialsOf(teacher.user.first_name, teacher.user.last_name)
              ) : (
                <UserIcon className="size-6" aria-hidden />
              )}
            </span>
          )}
          <div>
            <p className="text-lg font-bold uppercase tracking-tight text-ink">{fullName}</p>
            <p className="text-sm text-ink-secondary">{teacher.position || 'Тренер'}</p>
            <p className="mt-0.5 text-sm font-semibold text-brand-600">{formatMonthYear(report.year, report.month)}</p>
          </div>
        </div>

        <div className="flex justify-around gap-4 border-t border-border pt-4 sm:justify-end sm:gap-8 sm:border-t-0 sm:pt-0">
          {quickStats.map((stat) => (
            <div key={stat.label} className="text-center">
              <p className="text-xl font-bold text-ink">{stat.value}</p>
              <p className="text-xs text-ink-secondary">{stat.label}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
