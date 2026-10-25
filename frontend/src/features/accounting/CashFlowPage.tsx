import { useState } from 'react'
import { ArrowDownLeft, ArrowUpRight, Download } from 'lucide-react'
import { Link } from 'react-router-dom'

import { accountingApi } from '@/api/accounting'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { LoadingState } from '@/components/ui/LoadingState'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { StatCard } from '@/components/ui/StatCard'
import { StatGrid } from '@/components/ui/StatGrid'
import { useCashFlow } from '@/hooks/useAccounting'

import { METHOD_FILTER, RangePicker, rangeLabel, useFinanceRange } from './financeShared'
import { Section, formatDate, som, useRunner } from './shared'

const PAGE_SIZE = 50

const KIND_FILTER = [
  { value: 'student_payment', label: 'Платежи студентов' },
  { value: 'student_refund', label: 'Возвраты студентам' },
  { value: 'payroll_payment', label: 'Выплаты зарплаты' },
  { value: 'expense', label: 'Оплата расходов' },
]

/**
 * Касса: все фактические движения денег за период одной лентой — платежи
 * студентов (приход), возвраты, выплаты зарплаты и оплаченные расходы
 * (расход). Неоплаченные расходы и отменённые операции сюда не попадают.
 */
export function CashFlowPage() {
  const range = useFinanceRange()
  const [f, setF] = useState({ kind: '', method: '', direction: '', search: '', page: 1 })
  const set = (patch: Partial<typeof f>) => setF({ ...f, ...patch, page: patch.page ?? 1 })
  const params = { ...Object.fromEntries(Object.entries(f).filter(([, v]) => v !== '')), page_size: PAGE_SIZE }
  const flow = useCashFlow(range.params, params)
  const { run, busy } = useRunner()
  const d = flow.data

  return (
    <div>
      <PageHeader
        title="Касса и движение денег"
        description={d ? `${rangeLabel(d.date_from, d.date_to)}. ${d.note}` : 'Фактические поступления и выплаты за период.'}
        actions={(
          <Button variant="secondary" leftIcon={<Download className="size-4" />} isLoading={busy}
            onClick={() => run(() => accountingApi.downloadFinanceReport(range.params))}>
            Excel
          </Button>
        )}
      />
      <div className="mb-6"><RangePicker value={range.choice} onChange={(next) => { range.setChoice(next); set({}) }} /></div>

      {flow.isLoading ? <LoadingState /> : flow.isError || !d ? <ErrorState onRetry={() => flow.refetch()} /> : (
        <>
          <StatGrid>
            <StatCard label="Приход" value={som(d.summary.inflow)} icon={ArrowDownLeft} />
            <StatCard label="Расход" value={som(d.summary.outflow)} icon={ArrowUpRight} />
            <StatCard label="Сальдо за период" value={som(d.summary.net)} tone={Number(d.summary.net) < 0 ? 'danger' : 'default'}
              hint={`${d.summary.count} операций`} />
          </StatGrid>

          {d.summary.by_method.length ? (
            <Section title="По способам оплаты">
              <div className="card overflow-x-auto">
                <table className="data-table">
                  <thead><tr><th>Способ</th><th className="text-right">Приход</th><th className="text-right">Расход</th><th className="text-right">Сальдо</th></tr></thead>
                  <tbody>
                    {d.summary.by_method.map((m) => (
                      <tr key={m.method}>
                        <td className="font-medium text-ink">{m.method_display}</td>
                        <td className="text-right tabular-nums">{som(m.inflow)}</td>
                        <td className="text-right tabular-nums">{som(m.outflow)}</td>
                        <td className="text-right tabular-nums">{som(m.net)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Section>
          ) : null}

          <Section title="Операции">
            <FilterBar>
              <FilterField size="lg">
                <SearchInput aria-label="Поиск" placeholder="Контрагент, описание, документ" value={f.search}
                  onChange={(value) => set({ search: value })} />
              </FilterField>
              <FilterField>
                <Select aria-label="Операция" value={f.kind} placeholder="Все операции" options={KIND_FILTER}
                  onChange={(e) => set({ kind: e.target.value })} />
              </FilterField>
              <FilterField>
                <Select aria-label="Направление" value={f.direction} placeholder="Приход и расход"
                  options={[{ value: 'in', label: 'Приход' }, { value: 'out', label: 'Расход' }]}
                  onChange={(e) => set({ direction: e.target.value })} />
              </FilterField>
              <FilterField>
                <Select aria-label="Способ" value={f.method} placeholder="Все способы" options={METHOD_FILTER}
                  onChange={(e) => set({ method: e.target.value })} />
              </FilterField>
            </FilterBar>
            {d.results.length === 0 ? <EmptyState title="Движений денег за период нет" /> : (
              <div className="card overflow-x-auto">
                <table className="data-table">
                  <thead><tr><th>Дата</th><th>Операция</th><th>Контрагент</th><th>Описание</th><th>Способ</th><th className="text-right">Сумма</th></tr></thead>
                  <tbody>
                    {d.results.map((r) => (
                      <tr key={r.key}>
                        <td className="whitespace-nowrap">{formatDate(r.date)}</td>
                        <td><Badge tone={r.direction === 'in' ? 'success' : 'muted'}>{r.kind_display}</Badge></td>
                        <td className="font-medium text-ink">
                          <Link className="hover:underline" to={r.link}>{r.counterparty}</Link>
                        </td>
                        <td className="max-w-sm text-sm">
                          {r.description}
                          {r.reference ? <span className="block text-xs text-ink-muted">№ {r.reference}</span> : null}
                        </td>
                        <td className="whitespace-nowrap text-sm">{r.method_display}</td>
                        <td className={r.direction === 'in' ? 'whitespace-nowrap text-right tabular-nums text-brand-700' : 'whitespace-nowrap text-right tabular-nums'}>
                          {r.direction === 'in' ? '+' : '−'}{som(r.amount)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <Pagination page={f.page} pageSize={PAGE_SIZE} totalCount={d.count} onPageChange={(page) => set({ page })} />
          </Section>
        </>
      )}
    </div>
  )
}
