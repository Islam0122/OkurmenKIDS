import type { HomeworkResultStatus } from '@/types/homework'
import { HOMEWORK_RESULT_STATUS_LABELS } from '@/types/homework'
import { cn } from '@/utils/cn'

const STATUS_OPTIONS: { value: HomeworkResultStatus; label: string }[] = [
  { value: 'not_submitted', label: HOMEWORK_RESULT_STATUS_LABELS.not_submitted },
  { value: 'submitted', label: HOMEWORK_RESULT_STATUS_LABELS.submitted },
  { value: 'late', label: HOMEWORK_RESULT_STATUS_LABELS.late },
  { value: 'checked', label: HOMEWORK_RESULT_STATUS_LABELS.checked },
]

export interface HomeworkResultRow {
  student: number
  studentName: string
  status: HomeworkResultStatus
  score: number | null
  comment: string
}

export type HomeworkResultPatch = Partial<Pick<HomeworkResultRow, 'status' | 'score' | 'comment'>>

export interface HomeworkResultTableProps {
  rows: HomeworkResultRow[]
  onChange: (studentId: number, patch: HomeworkResultPatch) => void
  /** True when the viewer may not grade this homework (see
   * HomeworkSerializer.results_editable, enforced on the backend too), so
   * every control here becomes inert rather than merely styled differently.
   * A completed lesson never makes grading read-only. */
  readOnly?: boolean
}

export function HomeworkResultTable({ rows, onChange, readOnly = false }: HomeworkResultTableProps) {
  return (
    <ul className="divide-y divide-border card">
      {rows.map((row) => (
        <li key={row.student} className="flex flex-col gap-3 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-medium text-ink">{row.studentName}</span>
            <div role="radiogroup" aria-label={`Статус для ${row.studentName}`} className="flex flex-wrap gap-1.5">
              {STATUS_OPTIONS.map((option) => {
                const isActive = row.status === option.value
                return (
                  <button
                    key={option.value}
                    type="button"
                    role="radio"
                    aria-checked={isActive}
                    disabled={readOnly}
                    onClick={() => onChange(row.student, { status: option.value })}
                    className={cn(
                      'rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60',
                      isActive
                        ? 'border-brand-500 bg-brand-500 text-white'
                        : 'border-border bg-surface text-ink-secondary hover:enabled:bg-surface-hover',
                    )}
                  >
                    {option.label}
                  </button>
                )
              })}
            </div>
          </div>

          <div className="grid grid-cols-1 gap-2 sm:grid-cols-[auto_1fr] sm:items-center">
            <label className="flex items-center gap-2 text-sm text-ink-secondary">
              Балл
              <input
                type="number"
                inputMode="numeric"
                min={0}
                max={10}
                disabled={readOnly}
                value={row.score ?? ''}
                onChange={(event) => {
                  const raw = event.target.value
                  if (raw === '') {
                    onChange(row.student, { score: null })
                    return
                  }
                  const parsed = Math.min(10, Math.max(0, Number(raw)))
                  onChange(row.student, { score: parsed })
                }}
                className="form-control w-20 px-2"
              />
              / 10
            </label>
            <input
              type="text"
              disabled={readOnly}
              value={row.comment}
              onChange={(event) => onChange(row.student, { comment: event.target.value })}
              placeholder="Комментарий (необязательно)"
              className="form-control"
            />
          </div>
        </li>
      ))}
    </ul>
  )
}
