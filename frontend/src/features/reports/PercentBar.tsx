export interface PercentBarProps {
  label: string
  percent: number
  /** Tailwind width class for the label column — callers with longer
   * labels (KPI rows) need more room than short ones ("Неделя 1"). */
  labelClassName?: string
}

/** One compact `label ████████░░ NN%` row — the building block for both
 * the KPI breakdown and the weekly attendance dynamics, so a monthly
 * report never needs a full chart just to show four numbers. */
export function PercentBar({ label, percent, labelClassName = 'w-32' }: PercentBarProps) {
  const clamped = Math.max(0, Math.min(100, percent))
  return (
    <div className="flex items-center gap-3">
      <span className={`shrink-0 truncate text-sm text-ink-secondary ${labelClassName}`}>{label}</span>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-hover">
        <div className="h-full rounded-full bg-brand-500" style={{ width: `${clamped}%` }} />
      </div>
      <span className="w-12 shrink-0 text-right text-sm font-semibold text-ink">{percent}%</span>
    </div>
  )
}
