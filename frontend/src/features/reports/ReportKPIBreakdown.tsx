import type { MonthlyReportKPI } from '@/types/monthlyReport'
import { formatRuPercent } from '@/utils/format'

function KPICell({ label, percent }: { label: string; percent: number | null }) {
  const clamped = percent === null ? 0 : Math.max(0, Math.min(100, percent))
  return (
    <div>
      <p className="text-sm text-ink-secondary">{label}</p>
      <p className="mt-0.5 text-xl font-bold text-ink">{percent === null ? 'Нет данных' : formatRuPercent(percent)}</p>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-hover">
        <div className="h-full rounded-full bg-brand-500" style={{ width: `${clamped}%` }} />
      </div>
    </div>
  )
}

/** A compact 2x2 grid, not four bars stretched across the full card width. */
export function ReportKPIBreakdown({ kpi }: { kpi: MonthlyReportKPI }) {
  return (
    <div>
      <div className="grid grid-cols-2 gap-x-6 gap-y-5">
        <KPICell label="Посещаемость" percent={kpi.attendance} />
        <KPICell label="Домашние задания" percent={kpi.homework} />
        <KPICell label="Проведённые занятия" percent={kpi.lessons} />
        <KPICell label="Прогресс студентов" percent={kpi.student_progress} />
      </div>

      <div className="mt-5 flex items-center justify-between rounded-xl bg-brand-50 px-4 py-3.5">
        <p className="text-xs font-bold uppercase tracking-wide text-brand-700">Итоговый KPI</p>
        <p className="text-2xl font-bold text-brand-700">{formatRuPercent(kpi.total)}</p>
      </div>
    </div>
  )
}
