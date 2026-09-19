import type { MonthlyReportKPI } from '@/types/monthlyReport'

import { PercentBar } from './PercentBar'

export function ReportKPIBreakdown({ kpi }: { kpi: MonthlyReportKPI }) {
  return (
    <div className="space-y-3">
      <PercentBar label="Посещаемость" percent={kpi.attendance} labelClassName="w-36 sm:w-44" />
      <PercentBar label="Домашние задания" percent={kpi.homework} labelClassName="w-36 sm:w-44" />
      <PercentBar label="Проведённые занятия" percent={kpi.lessons} labelClassName="w-36 sm:w-44" />
      <PercentBar label="Прогресс студентов" percent={kpi.student_progress} labelClassName="w-36 sm:w-44" />

      <div className="mt-4 flex items-center justify-between rounded-xl bg-brand-50 px-4 py-3.5">
        <p className="text-xs font-bold uppercase tracking-wide text-brand-700">Итоговый KPI</p>
        <p className="text-2xl font-bold text-brand-700">{kpi.total}%</p>
      </div>
    </div>
  )
}
