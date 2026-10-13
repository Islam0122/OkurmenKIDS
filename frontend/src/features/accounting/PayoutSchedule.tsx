import { Fragment, useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import type { NotIncludedEarnings, PayoutScheduleEntry, PayoutScheduleItem, PayoutScheduleStatus } from '@/types/accounting'

import { formatDate, som } from './shared'

export const SCHEDULE_TONE: Record<PayoutScheduleStatus, BadgeTone> = {
  SCHEDULED: 'info',
  PARTIALLY_PAID: 'warning',
  PAID: 'success',
}

export function ItemLine({ item }: { item: PayoutScheduleItem }) {
  if (item.payroll_id) {
    return (
      <div>
        <p className="font-medium text-ink">Расчёт {item.period_label} · {item.payroll_status_display}</p>
        <ul className="text-ink-secondary">
          {(item.blocks ?? []).map((b, i) => (
            <li key={i}>
              {b.subject_name ? `${b.subject_name} · ${b.group_name}${b.cycle_number ? ` · блок ${b.cycle_number}` : ''}` : b.description}
              {b.completed_on ? `, завершён ${formatDate(b.completed_on)}` : ''}: {som(b.amount)}
            </li>
          ))}
        </ul>
      </div>
    )
  }
  return (
    <p>
      <span className="font-medium text-ink">{item.subject_name} · {item.group_name} · блок {item.cycle_number}</span>
      <span className="text-ink-secondary">
        {item.completed_on ? `, завершён ${formatDate(item.completed_on)}` : ''}
        {item.source === 'OPEN_BLOCK' ? `, проведено вами ${item.lessons_taught} из ${item.required_lessons} уроков` : ''}
        {' · '}{item.source_display}: {som(item.gross)}
      </span>
    </p>
  )
}

/** «График выплат»: суммы по плановым датам (15-е / 1-е). Каждая сумма — в
 * одной дате; незавершённые блоки — отдельно, ни в одну дату не входят.
 * Все цифры — из backend, здесь ничего не пересчитывается. */
export function PayoutSchedule({ schedule, notIncluded }: { schedule: PayoutScheduleEntry[]; notIncluded: NotIncludedEarnings }) {
  const [open, setOpen] = useState<string | null>(null)
  return (
    <div className="space-y-4">
      {schedule.length === 0 ? (
        <p className="text-sm text-ink-muted">Завершённой работы к выплате пока нет.</p>
      ) : (
        <div className="card overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th /><th>Дата выплаты</th><th className="text-right">Заработано</th><th className="text-right">Налог</th>
                <th className="text-right">Другие удержания</th><th className="text-right">На руки</th>
                <th className="text-right">Выплачено</th><th className="text-right">Остаток</th><th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {schedule.map((e) => {
                const key = e.date ?? 'none'
                return (
                  <Fragment key={key}>
                    <tr className="cursor-pointer hover:bg-surface-hover" onClick={() => setOpen(open === key ? null : key)}>
                      <td>{open === key ? <ChevronDown className="size-4" aria-hidden /> : <ChevronRight className="size-4" aria-hidden />}</td>
                      <td className="whitespace-nowrap">
                        <span className="font-medium">{e.date ? formatDate(e.date) : 'Дата не определена'}</span>
                        {e.date_note ? <p className="text-xs text-ink-muted">{e.date_note}</p> : null}
                        {!e.fully_official ? <p className="text-xs text-warning">{som(e.not_yet_official)} ещё не утверждено бухгалтерией</p> : null}
                      </td>
                      <td className="whitespace-nowrap text-right">{som(e.gross)}</td>
                      <td className="whitespace-nowrap text-right">{som(e.tax)}</td>
                      <td className="whitespace-nowrap text-right">{som(e.other_deductions)}</td>
                      <td className="whitespace-nowrap text-right">{som(e.net)}</td>
                      <td className="whitespace-nowrap text-right">{som(e.paid)}</td>
                      <td className={`whitespace-nowrap text-right ${Number(e.remaining) > 0 ? 'text-warning' : ''}`}>{som(e.remaining)}</td>
                      <td><Badge tone={SCHEDULE_TONE[e.status]}>{e.status_display}</Badge></td>
                    </tr>
                    {open === key ? (
                      <tr>
                        <td />
                        <td colSpan={8} className="space-y-2 bg-surface-muted text-sm">
                          {e.items.map((item, i) => <ItemLine key={i} item={item} />)}
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      {notIncluded.items.length ? (
        <div className="rounded-lg border border-border p-4 text-sm">
          <p className="font-medium text-ink">
            Ещё не включено в выплату: заработано {som(notIncluded.gross)}, на руки {som(notIncluded.net)}
            {Number(notIncluded.tax) + Number(notIncluded.other_deductions) > 0
              ? ` (налог ${som(notIncluded.tax)}, другие удержания ${som(notIncluded.other_deductions)})` : ''}
          </p>
          <p className="mb-2 text-ink-secondary">{notIncluded.note}</p>
          <div className="space-y-1">{notIncluded.items.map((item, i) => <ItemLine key={i} item={item} />)}</div>
        </div>
      ) : null}
    </div>
  )
}
