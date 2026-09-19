import type { MonthlyReportWeekPoint } from '@/types/monthlyReport'

import { PercentBar } from './PercentBar'

/** A compact `Неделя N ███░░ NN%` list — deliberately not a full chart.
 * Four numbers don't need 300px of SVG; this fits in ~150px regardless of
 * how many weeks there are. */
export function ReportWeeklyBars({ weeks }: { weeks: MonthlyReportWeekPoint[] }) {
  if (weeks.length < 2) {
    return <p className="text-sm text-ink-muted">Недостаточно данных для динамики.</p>
  }

  return (
    <div className="space-y-2.5">
      {weeks.map((week) => (
        <PercentBar key={week.label} label={week.label} percent={week.percent} labelClassName="w-20" />
      ))}
    </div>
  )
}
