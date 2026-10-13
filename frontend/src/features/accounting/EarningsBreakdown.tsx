import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import type { Earnings, EarningsSource } from '@/types/accounting'

import { formatDate, som } from './shared'

const SOURCE_TONE: Record<EarningsSource, BadgeTone> = {
  OPEN_BLOCK: 'info',
  ACCRUAL_PENDING: 'warning',
  PAYROLL_DRAFT: 'warning',
  PAYROLL_OFFICIAL: 'success',
  REVIEW: 'muted',
}

const SHORT: Record<EarningsSource, string> = {
  OPEN_BLOCK: 'Блок идёт',
  ACCRUAL_PENDING: 'Блок завершён',
  PAYROLL_DRAFT: 'Расчёт не утверждён',
  PAYROLL_OFFICIAL: 'Начислено официально',
  REVIEW: 'На проверке',
}

/** Из чего сложился заработок: блоки по предметам и группам, расчёты,
 * удержания и почему заработок отличается от официального начисления.
 * Все суммы — из backend (`earnings`), здесь ничего не пересчитывается. */
export function EarningsBreakdown({ data }: { data: Earnings }) {
  return (
    <div className="space-y-4">
      {data.difference_reasons.length ? (
        <div className="rounded-lg bg-surface-muted p-3 text-sm">
          <p className="font-medium text-ink">
            Заработано {som(data.earned.gross)}, официально начислено {som(data.official.gross)} — разница {som(data.difference)}:
          </p>
          <ul className="mt-1 space-y-0.5 text-ink-secondary">
            {data.difference_reasons.map((r) => <li key={r.source}>{r.label}: {som(r.amount)}</li>)}
          </ul>
        </div>
      ) : null}

      {data.items.length === 0 ? <p className="text-sm text-ink-muted">Проведённой работы пока нет.</p> : (
        <div className="card overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr><th>Работа</th><th>Период</th><th>Основание</th><th className="text-right">Заработано</th><th>Статус</th><th>Выплата</th></tr>
            </thead>
            <tbody>
              {data.items.map((item, i) => (
                <tr key={`${item.source}-${item.payroll_id ?? item.cycle_id}-${i}`} className={item.source === 'REVIEW' ? 'opacity-60' : undefined}>
                  <td>
                    {item.subject_name
                      ? <>{item.subject_name} · {item.group_name}<p className="text-xs text-ink-muted">{item.course_name} · блок {item.cycle_number}</p></>
                      : <>Расчёт зарплаты<p className="text-xs text-ink-muted">{item.payroll_status_display}</p></>}
                  </td>
                  <td className="whitespace-nowrap text-sm">{item.period_label}</td>
                  <td className="text-sm">
                    {item.formula ? (
                      <>
                        {item.lessons_taught !== null && item.lessons_taught !== undefined ? `${item.lessons_taught} из ${item.required_lessons} уроков проведено вами` : 'весь блок'}
                        <p className="text-xs text-ink-muted">{item.formula}</p>
                      </>
                    ) : (item.lines ?? []).map((l) => <p key={l.description} className="text-xs text-ink-secondary">{l.description}: {som(l.amount)}</p>)}
                  </td>
                  <td className="whitespace-nowrap text-right">{som(item.gross)}</td>
                  <td><Badge tone={SOURCE_TONE[item.source]}>{SHORT[item.source]}</Badge></td>
                  <td className="whitespace-nowrap text-sm">{item.planned_payment_date ? formatDate(item.planned_payment_date) : item.source === 'OPEN_BLOCK' ? 'после завершения блока' : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data.deductions.length ? (
        <div className="card overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr><th>Удержание с заработка</th><th>Месяц</th><th className="text-right">По правилу за месяц</th><th className="text-right">Удерживается</th></tr>
            </thead>
            <tbody>
              {data.deductions.map((d) => (
                <tr key={`${d.name}-${d.year}-${d.month}`}>
                  <td>{d.name}<p className="text-xs text-ink-muted">{d.kind_display}</p></td>
                  <td className="whitespace-nowrap">{d.period_label}</td>
                  <td className="whitespace-nowrap text-right">{som(d.month_amount)}</td>
                  <td className="whitespace-nowrap text-right">
                    {som(d.amount)}
                    {Number(d.remaining) > 0 ? <p className="text-xs text-ink-muted">не хватает заработка: {som(d.remaining)}</p> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="px-4 py-2 text-xs text-ink-muted">Ежемесячное удержание — один раз за месяц, не за каждый урок, предмет или блок.</p>
        </div>
      ) : null}
    </div>
  )
}
