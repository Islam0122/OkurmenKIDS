import { ProgressBar } from '@/components/ProgressBar'
import { t } from '@/i18n'

/** «Суроо 7 / 20» and the bar — one component for every mode; a mode may add
 * a counts line (`counts`, e.g. the exam's «answered · left»). */
export function TestProgress({ index, total, answered, counts }: {
  index: number
  total: number
  answered: number
  counts?: (answered: number, left: number) => string
}) {
  return (
    <div className="train__progress">
      <ProgressBar value={index + 1} max={total} label={t.training.progress(index + 1, total)} />
      {counts ? <p className="train__counts">{counts(answered, total - answered)}</p> : null}
    </div>
  )
}
