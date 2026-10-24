import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { financeApi } from '@/api/finance'
import { Card } from '@/components/ui/Card'
import { DataTable } from '@/components/ui/DataTable'
import type { PeriodReport } from '@/types/finance'

import { useFinancePeriod } from './period'
import { Amount, FINANCE_KEY, Loadable, Stat, formatDate, som } from './ui'

type Filters = Record<string, string | number | undefined>

export function usePeriodReport(filters: Filters = {}) {
  const { params } = useFinancePeriod()
  return useQuery({
    queryKey: [...FINANCE_KEY, 'period-report', params, filters],
    queryFn: () => financeApi.periodReport({ ...params, ...filters }),
    placeholderData: keepPreviousData,
  })
}

function Row({ label, value, strong, tone }: { label: string; value: string; strong?: boolean; tone?: 'danger' | 'muted' }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1">
      <dt className={tone === 'muted' ? 'text-ink-muted' : 'text-ink-secondary'}>{label}</dt>
      <dd className={`tabular-nums ${strong ? 'font-semibold' : ''} ${tone === 'danger' ? 'text-danger' : ''}`}>{value}</dd>
    </div>
  )
}

/** Деньги периода и долги периода — раздельно: поступление считается по дате
 * получения денег, начисление — по своему учебному периоду. */
export function PeriodReportView({ report: r, compact }: { report: PeriodReport; compact?: boolean }) {
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label={`Поступило: ${r.label}`} value={som(r.received.gross)} tone="brand"
          hint={`чистыми ${som(r.received.net)} · ${r.received.count} платежей`} />
        <Stat label={`Начислено за ${r.label}`} value={som(r.accrued.amount)} hint={`${r.accrued.count} начислений, ${r.accrued.students} студентов`} />
        <Stat label="Долг на конец периода" value={som(r.debt.closing)} tone="danger" hint={`на ${formatDate(r.date_to)}; на начало ${som(r.debt.opening)}`} />
        <Stat label="Долг периода погашен позже" value={som(r.accrued.paid_later)} tone="warning"
          hint={r.accrued.paid_later_by_month.map((m) => `${m.label}: ${som(m.amount)}`).join(' · ') || 'нет'} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Деньги, полученные в периоде" description={r.basis.received}>
          <dl className="text-sm">
            <Row label="За текущий период" value={som(r.received.for_current_period)} />
            <Row label="За прошлые периоды (погашение долгов)" value={som(r.received.for_previous_periods)} strong />
            {r.received.previous_by_period.map((m) => (
              <Row key={m.month} label={`— долг за ${m.label}`} value={som(m.amount)} tone="muted" />
            ))}
            <Row label="За будущие периоды" value={som(r.received.for_future_periods)} />
            <Row label="Осталось авансом / возвращено" value={som(r.received.to_credit)} />
            <Row label="Возвраты" value={`${som(r.received.refunds)} (${r.received.refunds_count})`} />
            {r.received.backdated.count ? (
              <Row label="Из них внесено задним числом" value={`${som(r.received.backdated.amount)} (${r.received.backdated.count})`} tone="muted" />
            ) : null}
          </dl>
        </Card>
        <Card title="Начисления периода" description={r.basis.accrued}>
          <dl className="text-sm">
            <Row label="Начислено" value={som(r.accrued.amount)} strong />
            <Row label="Оплачено заранее (аванс)" value={som(r.accrued.paid_in_advance)} />
            <Row label="Оплачено в периоде" value={som(r.accrued.paid_in_period)} />
            <Row label="Скорректировано до конца периода" value={som(r.accrued.adjusted_by_end)} />
            <Row label="Не оплачено на конец периода" value={som(r.accrued.unpaid_at_end)} strong tone="danger" />
            <Row label="Погашено позже" value={som(r.accrued.paid_later)} />
            {r.accrued.paid_later_by_month.map((m) => (
              <Row key={m.month} label={`— поступило в ${m.label}`} value={som(m.amount)} tone="muted" />
            ))}
            <Row label="Скорректировано позже" value={som(r.accrued.adjusted_later)} />
            <Row label="Не оплачено сейчас" value={som(r.accrued.unpaid_now)} strong />
          </dl>
        </Card>
      </div>
      {compact ? null : (
        <Card title={`Должники на ${formatDate(r.date_to)}`} description={r.basis.debt} padding="none">
          <DataTable rows={r.debtors_at_end} getRowKey={(d) => d.profile} columns={[
            { key: 's', header: 'Студент', render: (d) => (
              <Link to={`/finance/students/${d.profile}`} className="font-medium text-brand-700 hover:underline">{d.student_name}</Link>
            ) },
            { key: 'g', header: 'Группа', render: (d) => d.group ?? '—' },
            { key: 'p', header: 'Самый ранний период', render: (d) => formatDate(d.oldest_period) },
            { key: 'd', header: 'Долг на конец периода', render: (d) => <Amount value={d.debt} tone="danger" /> },
            { key: 'n', header: 'Не оплачено сейчас', render: (d) => <Amount value={d.unpaid_now} tone={d.unpaid_now === '0.00' ? 'muted' : undefined} /> },
          ]} />
          {r.debtors_at_end.length === 0 ? <p className="card-body text-sm text-ink-secondary">Долгов на конец периода нет.</p> : null}
        </Card>
      )}
    </div>
  )
}

export function PeriodReportCard({ filters, compact }: { filters?: Filters; compact?: boolean }) {
  const query = usePeriodReport(filters)
  return <Loadable query={query}>{(report) => <PeriodReportView report={report} compact={compact} />}</Loadable>
}
