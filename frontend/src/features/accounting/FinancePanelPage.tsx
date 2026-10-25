import { Download } from 'lucide-react'
import { Link } from 'react-router-dom'

import { accountingApi } from '@/api/accounting'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { StatCard } from '@/components/ui/StatCard'
import { StatGrid } from '@/components/ui/StatGrid'
import { useFinanceOverview } from '@/hooks/useAccounting'
import type { MetricChange } from '@/types/accounting'

import { HorizontalBars, MonthlyBarsChart } from './charts'
import { ChangeBadge, RangePicker, SHORT_MONTHS, rangeLabel, useFinanceRange } from './financeShared'
import { MONTHS, Notice, Section, som, useRunner } from './shared'

function ComparisonRow({ label, change, goodDirection }: { label: string; change: MetricChange; goodDirection: 'up' | 'down' }) {
  return (
    <tr>
      <td className="font-medium text-ink">{label}</td>
      <td className="text-right tabular-nums">{som(change.current)}</td>
      <td className="text-right tabular-nums">{som(change.previous)}</td>
      <td className="text-right"><ChangeBadge change={change} goodDirection={goodDirection} /></td>
    </tr>
  )
}

/**
 * Единая финансовая панель за период. Поступления, начисления студентам,
 * авансы, расходы, начисленная и выплаченная зарплата — разные величины:
 * каждая карточка подписана, а денежный результат считается только по
 * фактическому движению денег (кассовый метод).
 */
export function FinancePanelPage() {
  const range = useFinanceRange()
  const overview = useFinanceOverview(range.params)
  const { run, busy } = useRunner()
  const d = overview.data

  return (
    <div>
      <PageHeader
        title="Финансовая панель"
        description={d ? `Период ${rangeLabel(d.date_from, d.date_to)} · сравнение с ${rangeLabel(d.previous_period.date_from, d.previous_period.date_to)}` : 'Все разделы бухгалтерии за выбранный период.'}
        actions={(
          <Button variant="secondary" leftIcon={<Download className="size-4" />} isLoading={busy}
            onClick={() => run(() => accountingApi.downloadFinanceReport(range.params))}>
            Excel
          </Button>
        )}
      />
      <div className="mb-6"><RangePicker value={range.choice} onChange={range.setChoice} /></div>

      {overview.isLoading ? <LoadingState /> : overview.isError || !d ? <ErrorState onRetry={() => overview.refetch()} /> : (
        <>
          <Section title="Денежный поток (кассовый метод)">
            <StatGrid>
              <StatCard label="Приход: платежи студентов" value={som(d.cash_flow.inflow)} hint={`${d.students.count} платежей`} />
              <StatCard label="Расход: всего" value={som(d.cash_flow.outflow)}
                hint={`возвраты ${som(d.cash_flow.outflow_refunds)} · зарплата ${som(d.cash_flow.outflow_payroll)} · расходы ${som(d.cash_flow.outflow_expenses)}`} />
              <StatCard label="Денежный результат" value={som(d.result.cash)} tone={Number(d.result.cash) < 0 ? 'danger' : 'default'}
                hint={d.result.cash_basis} />
            </StatGrid>
            <p className="mt-2 text-xs text-ink-secondary">{d.result.accrual_note}</p>
          </Section>

          <Section title="Оплата студентов" actions={<Link className="text-sm text-brand-700 hover:underline" to="/finance/analytics">Подробно →</Link>}>
            <StatGrid>
              <StatCard label="Поступило (чистые)" value={som(d.students.net)} hint={`валовые ${som(d.students.gross)} − возвраты ${som(d.students.refunds)}`} />
              <StatCard label="Выставлено начислений" value={som(d.students.invoiced)}
                hint="требование оплаты за учебные месяцы периода — не доход и не деньги" />
              <StatCard label="Задолженность студентов" value={som(d.students.debt_now)} tone={Number(d.students.debt_now) > 0 ? 'warning' : 'default'}
                hint={`на конец периода ${som(d.students.debt_end)} · просрочено сейчас ${som(d.students.overdue_now)}`} />
              <StatCard label="Остатки авансов" value={som(d.students.prepayment)}
                hint={`обязательство перед родителями · не распределено ${som(d.students.unallocated_credit)}`} />
            </StatGrid>
            {d.students.prepayment_review ? (
              <div className="mt-3">
                <Notice tone="warning" items={[`Требуют проверки авансы у ${d.students.prepayment_review} договоров — откройте «Авансы».`]} />
              </div>
            ) : null}
          </Section>

          <Section title="Зарплата сотрудников" actions={<Link className="text-sm text-brand-700 hover:underline" to="/accounting/analytics">Подробно →</Link>}>
            <StatGrid>
              <StatCard label="Начислено (утверждено)" value={som(d.payroll.accrued)}
                hint={Number(d.payroll.awaiting_approval) ? `ещё ${som(d.payroll.awaiting_approval)} ждёт утверждения` : `сотрудников: ${d.payroll.employees}`} />
              <StatCard label="Выплачено в периоде" value={som(d.payroll.paid_cash)} hint={`${d.payroll.paid_cash_count} выплат, за любые месяцы`} />
              <StatCard label="Удержано" value={som(d.payroll.deductions)} />
              <StatCard label="Долг перед сотрудниками" value={som(d.payroll.outstanding_now)}
                tone={Number(d.payroll.outstanding_now) > 0 ? 'warning' : 'default'} hint="утверждено и не выплачено, на сегодня" />
            </StatGrid>
          </Section>

          <Section title="Расходы компании" actions={<Link className="text-sm text-brand-700 hover:underline" to="/accounting/expenses?tab=report">По категориям →</Link>}>
            <StatGrid>
              <StatCard label="Оплачено в периоде" value={som(d.expenses.paid)} />
              <StatCard label="Начислено по дате расхода" value={som(d.expenses.incurred)} hint="оплаченные и неоплаченные" />
              <StatCard label="Не оплачено сейчас" value={som(d.expenses.unpaid_now_amount)}
                tone={Number(d.expenses.unpaid_now_amount) > 0 ? 'warning' : 'default'} hint={`${d.expenses.unpaid_now_count} расходов`} />
              <StatCard label="Просрочено поставщикам" value={som(d.expenses.unpaid_now_overdue_amount)}
                tone={Number(d.expenses.unpaid_now_overdue_amount) > 0 ? 'danger' : 'default'} />
            </StatGrid>
          </Section>

          <div className="mt-6 grid gap-4 lg:grid-cols-2">
            <div className="min-w-0 lg:col-span-2">
              <MonthlyBarsChart title="Приход и расход по месяцам" labels={['Приход', 'Расход']}
                points={d.history.map((h) => ({ label: `${SHORT_MONTHS[h.month - 1]} ${String(h.year).slice(2)}`, accrued: Number(h.inflow), paid: Number(h.outflow) }))} />
            </div>
            <HorizontalBars title="Структура расхода за период"
              rows={[
                { label: 'Зарплата', value: Number(d.cash_flow.outflow_payroll) },
                { label: 'Расходы компании', value: Number(d.cash_flow.outflow_expenses) },
                { label: 'Возвраты студентам', value: Number(d.cash_flow.outflow_refunds) },
              ]} />
            <HorizontalBars title="Поступления по способам оплаты"
              rows={d.cash_flow.by_method.map((m) => ({ label: m.method_display, value: Number(m.inflow),
                hint: `приход ${som(m.inflow)} · расход ${som(m.outflow)} · сальдо ${som(m.net)}` }))} />
          </div>

          <Section title="Сравнение с предыдущим периодом">
            <div className="card overflow-x-auto">
              <table className="data-table">
                <thead><tr><th>Показатель</th><th className="text-right">Сейчас</th><th className="text-right">Ранее</th><th className="text-right">Изменение</th></tr></thead>
                <tbody>
                  <ComparisonRow label="Поступления студентов (чистые)" change={d.comparison.student_receipts} goodDirection="up" />
                  <ComparisonRow label="Начислено зарплаты" change={d.comparison.payroll_accrued} goodDirection="down" />
                  <ComparisonRow label="Выплачено зарплаты" change={d.comparison.payroll_paid} goodDirection="down" />
                  <ComparisonRow label="Оплаченные расходы" change={d.comparison.expenses_paid} goodDirection="down" />
                  <ComparisonRow label="Денежный поток" change={d.comparison.cash_flow_net} goodDirection="up" />
                </tbody>
              </table>
            </div>
          </Section>

          <Section title="Движение денег по месяцам" actions={<Link className="text-sm text-brand-700 hover:underline" to="/accounting/cash">Касса →</Link>}>
            <div className="card overflow-x-auto">
              <table className="data-table">
                <thead><tr><th>Месяц</th><th className="text-right">Поступило</th><th className="text-right">Возвраты</th><th className="text-right">Зарплата</th><th className="text-right">Расходы</th><th className="text-right">Чистый поток</th></tr></thead>
                <tbody>
                  {[...d.history].reverse().map((h) => (
                    <tr key={`${h.year}-${h.month}`}>
                      <td>{MONTHS[h.month - 1]} {h.year}</td>
                      <td className="text-right tabular-nums">{som(h.inflow)}</td>
                      <td className="text-right tabular-nums">{som(h.refunds)}</td>
                      <td className="text-right tabular-nums">{som(h.payroll)}</td>
                      <td className="text-right tabular-nums">{som(h.expenses)}</td>
                      <td className={Number(h.net) < 0 ? 'text-right tabular-nums text-danger' : 'text-right tabular-nums'}>{som(h.net)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>

          {!d.branches_supported ? (
            <p className="mt-4 text-xs text-ink-muted">Филиалов в системе нет — отчёты строятся по всей компании.</p>
          ) : null}
        </>
      )}
    </div>
  )
}
