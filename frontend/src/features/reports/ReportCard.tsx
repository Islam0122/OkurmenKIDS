import { ArrowRight, FileText } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Badge } from '@/components/ui/Badge'
import type { MonthlyTeacherReport } from '@/types/monthlyReport'
import { formatMonthYear } from '@/utils/format'

export function ReportCard({ report }: { report: MonthlyTeacherReport }) {
  const { stats } = report

  return (
    <Link
      to={`/app/reports/${report.id}`}
      className="block rounded-xl border border-border bg-surface p-5 transition-colors hover:border-brand-200 hover:bg-brand-50/30"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
            <FileText className="size-4" aria-hidden />
          </span>
          <h3 className="font-semibold text-ink">{formatMonthYear(report.year, report.month)}</h3>
        </div>
        <Badge tone="success">Создан</Badge>
      </div>

      {stats.has_data ? (
        <p className="mt-4 text-sm text-ink-secondary">
          {stats.lessons_completed} занятия · {stats.students_count} студента · {stats.groups_count} группы
        </p>
      ) : (
        <p className="mt-4 text-sm text-ink-muted">Нет данных за этот месяц</p>
      )}

      <div className="mt-4 flex items-center justify-between border-t border-border pt-3">
        {stats.has_data ? (
          <p className="text-sm">
            <span className="text-ink-secondary">KPI </span>
            <span className="font-semibold text-ink">{stats.kpi.total}%</span>
          </p>
        ) : (
          <span />
        )}
        <span className="inline-flex items-center gap-1 text-sm font-medium text-brand-600">
          Открыть <ArrowRight className="size-3.5" aria-hidden />
        </span>
      </div>
    </Link>
  )
}
