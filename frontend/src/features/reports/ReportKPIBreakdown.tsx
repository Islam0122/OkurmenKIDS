import type { MonthlyReportKPI } from '@/types/monthlyReport'

function KPIBar({ label, percent }: { label: string; percent: number }) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-32 shrink-0 text-sm text-ink-secondary">{label}</span>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-hover">
        <div className="h-full rounded-full bg-brand-500" style={{ width: `${Math.max(0, Math.min(100, percent))}%` }} />
      </div>
      <span className="w-12 shrink-0 text-right text-sm font-semibold text-ink">{percent}%</span>
    </div>
  )
}

export function ReportKPIBreakdown({ kpi }: { kpi: MonthlyReportKPI }) {
  return (
    <div className="space-y-3">
      <KPIBar label="Attendance" percent={kpi.attendance} />
      <KPIBar label="Homework" percent={kpi.homework} />
      <KPIBar label="Lessons" percent={kpi.lessons} />
      <KPIBar label="Student Progress" percent={kpi.student_progress} />

      <div className="mt-4 flex items-center justify-between rounded-xl bg-brand-50 px-4 py-3.5">
        <p className="text-xs font-bold uppercase tracking-wide text-brand-700">Total KPI</p>
        <p className="text-2xl font-bold text-brand-700">{kpi.total}%</p>
      </div>
    </div>
  )
}
