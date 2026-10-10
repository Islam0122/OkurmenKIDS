import { useState } from 'react'
import { AlertTriangle, CalendarClock, ClipboardCheck, Users } from 'lucide-react'
import { Link } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { TrendChart } from '@/components/charts/TrendChart'
import { Badge } from '@/components/ui/Badge'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { LoadingState } from '@/components/ui/LoadingState'
import { Select } from '@/components/ui/Select'
import { StatCard } from '@/components/ui/StatCard'
import { StatGrid } from '@/components/ui/StatGrid'
import { useAccountingOptions, useAnalyticsSummary } from '@/hooks/useAccounting'
import type { AnalyticsFilters, Department } from '@/types/accounting'

import { HorizontalBars, MonthlyBarsChart } from './charts'
import { MONTHS, Section, formatDate, som } from './shared'

const SHORT = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']

export function currentMonth(): AnalyticsFilters {
  const now = new Date()
  return { year: now.getFullYear(), month: now.getMonth() + 1 }
}

/** Месяц, год и направление — общий фильтр аналитики и отчётов. */
export function MonthFilters({ value, onChange, departments }: {
  value: AnalyticsFilters
  onChange: (next: AnalyticsFilters) => void
  departments: { value: string; label: string }[]
}) {
  const year = new Date().getFullYear()
  return (
    <FilterBar>
      <FilterField>
        <Select aria-label="Месяц" value={String(value.month)} options={MONTHS.map((label, i) => ({ value: String(i + 1), label }))}
          onChange={(e) => onChange({ ...value, month: Number(e.target.value) })} />
      </FilterField>
      <FilterField>
        <Select aria-label="Год" value={String(value.year)}
          options={[year - 2, year - 1, year].map((y) => ({ value: String(y), label: String(y) }))}
          onChange={(e) => onChange({ ...value, year: Number(e.target.value) })} />
      </FilterField>
      <FilterField>
        <Select aria-label="Направление" value={value.department ?? ''} placeholder="Все направления" options={departments}
          onChange={(e) => onChange({ ...value, department: (e.target.value || undefined) as Department | undefined })} />
      </FilterField>
    </FilterBar>
  )
}

/**
 * Финансовая аналитика директора — только чтение. Все показатели считает
 * backend по утверждённым начислениям; предварительные оценки сюда не входят,
 * а денежные переводы месяца показаны отдельно от начислений месяца.
 */
export function AnalyticsPage() {
  const [filters, setFilters] = useState<AnalyticsFilters>(currentMonth)
  const options = useAccountingOptions()
  const summary = useAnalyticsSummary(filters)
  const d = summary.data

  const change = d ? Number(d.accrued_change) : 0
  return (
    <div>
      <PageHeader
        title="Финансовая аналитика"
        description="Начислено — утверждённые начисления месяца; выплачено — переводы по ним; остаток — разница. Денежные переводы месяца могут относиться к начислениям прошлых месяцев и показаны отдельно."
      />
      <MonthFilters value={filters} onChange={setFilters} departments={options.data?.departments ?? []} />

      {summary.isLoading ? <LoadingState /> : summary.isError || !d ? <ErrorState onRetry={() => summary.refetch()} /> : (
        <>
          <StatGrid>
            <StatCard label="Начислено за месяц" value={som(d.accrued)}
              hint={`к прошлому месяцу (${som(d.previous_month.accrued)}): ${change > 0 ? '+' : ''}${som(d.accrued_change)}${
                d.accrued_change_percent !== null ? ` (${change > 0 ? '+' : ''}${Number(d.accrued_change_percent)}%)` : ''}`} />
            <StatCard label="Выплачено по начислениям месяца" value={som(d.paid)}
              hint={`переводов в этом месяце: ${som(d.cash_paid_in_month)}`} />
            <StatCard label="Остаток задолженности" value={som(d.outstanding)} tone={Number(d.outstanding) > 0 ? 'warning' : 'default'} />
            <StatCard label="Сотрудников с начислениями" value={d.employees} icon={Users}
              hint={Number(d.awaiting_approval_amount) ? `ещё ${som(d.awaiting_approval_amount)} ждёт утверждения` : undefined} />
          </StatGrid>

          <div className="mt-4 flex flex-wrap gap-2 text-sm">
            <Badge tone={d.pending_approval_count ? 'warning' : 'muted'}>
              <ClipboardCheck className="mr-1 inline size-3" aria-hidden />Ожидают утверждения: {d.pending_approval_count}
            </Badge>
            <Badge tone={d.review_required_count ? 'warning' : 'muted'}>
              <AlertTriangle className="mr-1 inline size-3" aria-hidden />Блоки на проверке: {d.review_required_count}
            </Badge>
            <Badge tone="muted">Открытых блоков: {d.open_cycles}</Badge>
          </div>

          <div className="mt-6 grid gap-4 lg:grid-cols-2">
            <MonthlyBarsChart title="Начислено и выплачено по месяцам"
              points={d.history.map((h) => ({ label: `${SHORT[h.month - 1]} ${String(h.year).slice(2)}`, accrued: Number(h.accrued), paid: Number(h.paid) }))} />
            <HorizontalBars title="Расходы по направлениям"
              rows={d.by_department.map((r) => ({ label: r.label, value: Number(r.accrued), hint: `сотрудников: ${r.employees}` }))} />
            <TrendChart title="Фонд оплаты труда (начислено), сом"
              points={d.history.map((h) => ({ label: `${SHORT[h.month - 1]} ${String(h.year).slice(2)}`, value: Number(h.accrued) }))}
              max={Math.max(1, ...d.history.map((h) => Number(h.accrued)))} />
            <TrendChart title="Остаток задолженности по месяцам, сом" color="var(--color-warning)"
              points={d.history.map((h) => ({ label: `${SHORT[h.month - 1]} ${String(h.year).slice(2)}`, value: Number(h.outstanding) }))}
              max={Math.max(1, ...d.history.map((h) => Number(h.outstanding)))} />
          </div>

          <Section title="Расходы по направлениям">
            <div className="card overflow-x-auto">
              <table className="data-table">
                <thead><tr><th>Направление</th><th className="text-right">Сотрудников</th><th className="text-right">Начислено</th><th className="text-right">Выплачено</th><th className="text-right">Остаток</th></tr></thead>
                <tbody>
                  {d.by_department.map((r) => (
                    <tr key={r.department}>
                      <td className="font-medium text-ink">{r.label}</td>
                      <td className="text-right">{r.employees}</td>
                      <td className="text-right">{som(r.accrued)}</td>
                      <td className="text-right">{som(r.paid)}</td>
                      <td className="text-right">{som(r.outstanding)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>

          <Section title="Ближайшие плановые выплаты" actions={<Link className="text-sm text-brand-700 hover:underline" to="/accounting/reports">Отчёт по сотрудникам →</Link>}>
            {d.upcoming_payments.length === 0 ? <EmptyState title="Утверждённых остатков к выплате нет" /> : (
              <div className="card overflow-x-auto">
                <table className="data-table">
                  <thead><tr><th>Плановая дата</th><th>Сотрудник</th><th>Период</th><th className="text-right">Остаток</th><th>Статус</th></tr></thead>
                  <tbody>
                    {d.upcoming_payments.map((p) => (
                      <tr key={p.payroll_id}>
                        <td className="whitespace-nowrap">
                          <CalendarClock className="mr-1 inline size-3.5 text-ink-muted" aria-hidden />
                          {p.planned_payment_date ? formatDate(p.planned_payment_date) : <span className="text-xs text-ink-muted">календарь оклада не настроен</span>}
                          {p.is_overdue ? <Badge className="ml-2" tone="danger">просрочено</Badge> : null}
                        </td>
                        <td><Link className="text-brand-700 hover:underline" to={`/accounting/payrolls/${p.payroll_id}`}>{p.employee_name}</Link></td>
                        <td>{p.period_label}</td>
                        <td className="text-right">{som(p.due)}</td>
                        <td>{p.status_display}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>

          <Section title="История по месяцам">
            <div className="card overflow-x-auto">
              <table className="data-table">
                <thead><tr><th>Месяц</th><th className="text-right">Начислено</th><th className="text-right">Выплачено по начислениям</th><th className="text-right">Остаток</th><th className="text-right">Переводы в месяце</th></tr></thead>
                <tbody>
                  {[...d.history].reverse().map((h) => (
                    <tr key={`${h.year}-${h.month}`}>
                      <td>{MONTHS[h.month - 1]} {h.year}</td>
                      <td className="text-right">{som(h.accrued)}</td>
                      <td className="text-right">{som(h.paid)}</td>
                      <td className="text-right">{som(h.outstanding)}</td>
                      <td className="text-right">{som(h.cash_paid)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>
        </>
      )}
    </div>
  )
}
