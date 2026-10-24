import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { financeApi } from '@/api/finance'
import { PageHeader } from '@/components/layout/PageHeader'
import { Card } from '@/components/ui/Card'
import { DataTable } from '@/components/ui/DataTable'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'

import { PeriodReportCard } from './PeriodReportCard'
import { useFinancePeriod } from './period'
import { Amount, FINANCE_KEY, Loadable, Stat, som, useFinanceOptions } from './ui'

/** «Фактически получено» и «Ожидалось получить» — два независимых показателя:
 * деньги по дате поступления и начисления по сроку оплаты. Период — общий
 * переключатель раздела (месяц или произвольный диапазон); «С/По» здесь его меняют. */
export function AnalyticsPage() {
  const options = useFinanceOptions()
  const period = useFinancePeriod()
  const [f, setF] = useState({ program: '', group: '', method: '', status: '' })
  const params = { ...Object.fromEntries(Object.entries(f).filter(([, v]) => v !== '')),
    date_from: period.date_from, date_to: period.date_to }
  const query = useQuery({
    queryKey: [...FINANCE_KEY, 'analytics', params],
    queryFn: () => financeApi.analytics(params),
    placeholderData: keepPreviousData,
  })
  const set = (patch: Partial<typeof f>) => setF({ ...f, ...patch })
  return (
    <div>
      <PageHeader title="Аналитика" description="Полученные деньги и ожидаемые поступления считаются раздельно и не смешиваются." />
      <FilterBar>
        <FilterField label="С" htmlFor="an-from"><Input id="an-from" type="date" value={period.date_from} max={period.date_to}
          onChange={(e) => e.target.value && period.setPeriod({ kind: 'range', date_from: e.target.value, date_to: period.date_to })} /></FilterField>
        <FilterField label="По" htmlFor="an-to"><Input id="an-to" type="date" value={period.date_to} min={period.date_from}
          onChange={(e) => e.target.value && period.setPeriod({ kind: 'range', date_from: period.date_from, date_to: e.target.value })} /></FilterField>
        <FilterField>
          <Select aria-label="Программа" value={f.program} placeholder="Все программы" onChange={(e) => set({ program: e.target.value })}
            options={(options.data?.programs ?? []).map((p) => ({ value: String(p.id), label: p.name }))} />
        </FilterField>
        <FilterField>
          <Select aria-label="Группа" value={f.group} placeholder="Все группы" onChange={(e) => set({ group: e.target.value })}
            options={(options.data?.groups ?? []).map((g) => ({ value: String(g.id), label: g.name }))} />
        </FilterField>
        <FilterField>
          <Select aria-label="Способ оплаты" value={f.method} placeholder="Все способы" onChange={(e) => set({ method: e.target.value })}
            options={options.data?.payment_methods ?? []} />
        </FilterField>
        <FilterField>
          <Select aria-label="Статус начисления" value={f.status} placeholder="Все статусы" onChange={(e) => set({ status: e.target.value })}
            options={options.data?.invoice_statuses ?? []} />
        </FilterField>
      </FilterBar>
      <div className="mt-4 space-y-4">
        <PeriodReportCard filters={{ group: f.group || undefined }} />
        <Loadable query={query}>
          {(a) => (
            <div className="space-y-4">
              <div className="grid gap-4 lg:grid-cols-2">
                <Card title="Фактически получено" description={a.received.basis}>
                  <p className="text-3xl font-semibold tabular-nums text-brand-700">{som(a.received.gross)}</p>
                  <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
                    <dt className="text-ink-secondary">Платежей</dt><dd>{a.received.count}</dd>
                    <dt className="text-ink-secondary">Возвраты</dt><dd>{som(a.received.refunds)} ({a.received.refunds_count})</dd>
                    <dt className="font-medium">Чистый денежный поток</dt><dd className="font-semibold">{som(a.received.net)}</dd>
                    <dt className="text-ink-secondary">Сторнировано (не входит)</dt><dd>{som(a.received.reversed)} ({a.received.reversed_count})</dd>
                    {a.received.by_method.map((m) => (
                      <div key={m.method} className="contents"><dt className="text-ink-secondary">— {m.method_display}</dt><dd>{som(m.amount)}</dd></div>
                    ))}
                  </dl>
                </Card>
                <Card title="Ожидалось получить" description={a.expected.basis}>
                  <p className="text-3xl font-semibold tabular-nums text-ink">{som(a.expected.amount)}</p>
                  <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
                    <dt className="text-ink-secondary">Начислений / студентов</dt><dd>{a.expected.count} / {a.expected.students}</dd>
                    <dt className="text-ink-secondary">Из них оплачено</dt><dd>{som(a.expected.paid)}</dd>
                    <dt className="text-ink-secondary">Не оплачено</dt><dd className="font-semibold text-danger">{som(a.expected.unpaid)}</dd>
                    <dt className="text-ink-secondary">Оплачено полностью</dt><dd>{a.expected.paid_count}</dd>
                    <dt className="text-ink-secondary">Частично</dt><dd>{a.expected.partial_count}</dd>
                    <dt className="text-ink-secondary">Просрочено</dt><dd>{a.expected.overdue_count}</dd>
                  </dl>
                </Card>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
                <Stat label="Разница ожидалось − получено" value={som(a.difference)} />
                <Stat label="Долг на конец периода" value={som(a.debt_end)} tone="danger" />
                <Stat label="Скидки (не деньги)" value={som(a.discounts.amount)} hint={`${a.discounts.contracts} договоров`} />
                <Stat label="Брони" value={som(a.reservations)} />
                <Stat label="Предоплата" value={som(a.prepayment)} />
                <Stat label="Возвраты" value={som(a.received.refunds)} />
              </div>
              <Card title="По программам" padding="none">
                <DataTable rows={a.by_program} getRowKey={(r) => r.program ?? 0} columns={[
                  { key: 'n', header: 'Программа', render: (r) => <span className="font-medium">{r.program_name}</span> },
                  { key: 'r', header: 'Получено', render: (r) => <Amount value={r.received} /> },
                  { key: 'rf', header: 'Возвраты', render: (r) => <Amount value={r.refunded} tone="muted" /> },
                  { key: 'net', header: 'Чистый поток', render: (r) => <Amount value={r.net} tone="brand" /> },
                  { key: 'e', header: 'Ожидалось', render: (r) => <Amount value={r.expected} /> },
                  { key: 'u', header: 'Не оплачено', render: (r) => <Amount value={r.expected_unpaid} tone={r.expected_unpaid !== '0.00' ? 'danger' : 'muted'} /> },
                ]} />
              </Card>
            </div>
          )}
        </Loadable>
      </div>
    </div>
  )
}
