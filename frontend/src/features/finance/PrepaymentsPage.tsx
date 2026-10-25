import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'

import { financeApi } from '@/api/finance'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import { BackLink } from '@/components/ui/BackLink'
import { DataTable } from '@/components/ui/DataTable'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import type { PrepaymentRow, PrepaymentStatus } from '@/types/finance'

import { Amount, FINANCE_KEY, Loadable, Stat, som, useFinanceOptions } from './ui'

const STATUS_TONE: Record<PrepaymentStatus, BadgeTone> = { full: 'success', partial: 'info', advance: 'muted', review: 'warning' }

function StatusBadge({ row }: { row: PrepaymentRow }) {
  return (
    <span title={row.review_reasons.join(' ') || undefined}>
      <Badge tone={STATUS_TONE[row.status]}>{row.status_display}</Badge>
    </span>
  )
}

function months(row: PrepaymentRow): string {
  const total = row.duration_months ? ` из ${row.duration_months}` : ''
  return `${row.paid_months}${total}`
}

/** Детализация карточки «Остаток предоплаты за обучение»: кто оплатил заранее,
 * сколько уже использовано и сколько осталось на будущие месяцы. Все суммы —
 * из backend (`prepayments/`), итог совпадает с карточкой дашборда. */
export function PrepaymentsPage() {
  const navigate = useNavigate()
  const options = useFinanceOptions()
  const [f, setF] = useState({ search: '', program: '', group: '', status: '' })
  const params = Object.fromEntries(Object.entries(f).filter(([, v]) => v !== ''))
  const query = useQuery({
    queryKey: [...FINANCE_KEY, 'prepayments', params],
    queryFn: () => financeApi.prepayments(params),
    placeholderData: keepPreviousData,
  })
  const set = (patch: Partial<typeof f>) => setF({ ...f, ...patch })
  return (
    <div>
      <BackLink to="/finance">Dashboard</BackLink>
      <PageHeader title="Остаток предоплаты за обучение"
        description="Деньги, полученные от родителей за обучение заранее и ещё не зачтённые в оплату учебных месяцев." />
      <Loadable query={query}>
        {(data) => {
          const s = data.summary
          const d = s.definitions
          return (
            <>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <Stat label="Общий остаток предоплаты" value={som(s.prepayment)} tone="brand" hint={d.prepayment} />
                <Stat label="Учеников с предоплатой" value={s.students}
                  hint={`остаток аванса: ${s.advance}, требует проверки: ${s.review}`} />
                <Stat label="Полная предоплата" value={s.full} hint={d.full} />
                <Stat label="Частичная предоплата" value={s.partial} hint={d.partial} />
                <Stat label="Уже распределено на будущие месяцы" value={som(s.allocated_future)} hint={d.allocated_future} />
                <Stat label="Пока не распределено по счетам" value={som(s.unallocated)} hint={d.unallocated} />
              </div>
              {s.reservation_held !== '0.00' ? (
                <p className="mt-2 text-sm text-ink-secondary">Депозиты брони, ещё не зачтённые по договору: {som(s.reservation_held)} — в остаток не входят.</p>
              ) : null}
            </>
          )
        }}
      </Loadable>
      <div className="mt-4">
        <FilterBar>
          <FilterField size="lg"><SearchInput value={f.search} onChange={(search) => set({ search })} placeholder="Имя ученика" /></FilterField>
          <FilterField>
            <Select aria-label="Программа" value={f.program} placeholder="Все программы" onChange={(e) => set({ program: e.target.value })}
              options={(options.data?.programs ?? []).map((p) => ({ value: String(p.id), label: p.name }))} />
          </FilterField>
          <FilterField>
            <Select aria-label="Группа" value={f.group} placeholder="Все группы" onChange={(e) => set({ group: e.target.value })}
              options={(options.data?.groups ?? []).map((g) => ({ value: String(g.id), label: g.name }))} />
          </FilterField>
          <FilterField>
            <Select aria-label="Статус" value={f.status} placeholder="Все статусы" onChange={(e) => set({ status: e.target.value })}
              options={[{ value: 'full', label: 'Полная предоплата' }, { value: 'partial', label: 'Частичная предоплата' },
                { value: 'advance', label: 'Остаток аванса' }, { value: 'review', label: 'Требует проверки' }]} />
          </FilterField>
        </FilterBar>
      </div>
      <div className="mt-4">
        <Loadable query={query} empty={(d) => d.results.length === 0} emptyTitle="Учеников с предоплатой нет">
          {(data) => (
            <>
              <div className="hidden md:block">
                <DataTable rows={data.results} getRowKey={(r) => r.profile} onRowClick={(r) => navigate(`/finance/students/${r.profile}`)} columns={[
                  { key: 's', header: 'Ученик', render: (r) => <span className="font-medium">{r.student_name}</span> },
                  { key: 'p', header: 'Программа и группа', render: (r) => (
                    <div><p>{r.program}</p><p className="text-xs text-ink-secondary">{r.group ?? 'без группы'}</p></div>
                  ) },
                  { key: 't', header: 'Стоимость по договору', render: (r) => r.contract_total ? <Amount value={r.contract_total} /> : '—' },
                  { key: 'r', header: 'Получено', render: (r) => <Amount value={r.received} /> },
                  { key: 'u', header: 'Зачтено в обучение', render: (r) => <Amount value={r.applied_to_studied} tone="muted" /> },
                  { key: 'b', header: 'Остаток предоплаты', render: (r) => (
                    <div title={`на будущие месяцы ${som(r.allocated_future)}${r.allocated_future_exact ? '' : ' (оценка равными долями)'} · не распределено ${som(r.unallocated)}`}>
                      <Amount value={r.prepayment} tone="brand" />
                    </div>
                  ) },
                  { key: 'm', header: 'Оплачено месяцев', render: (r) => months(r) },
                  { key: 'n', header: 'Следующий месяц из предоплаты', render: (r) => r.next_covered_month ? `№${r.next_covered_month}` : '—' },
                  { key: 'st', header: 'Статус', render: (r) => <StatusBadge row={r} /> },
                ]} />
              </div>
              <ul className="space-y-2 md:hidden" aria-label="Ученики с предоплатой">
                {data.results.map((r) => (
                  <li key={r.profile} className="card p-3 text-sm">
                    <div className="flex items-start justify-between gap-2">
                      <Link to={`/finance/students/${r.profile}`} className="font-medium text-brand-700">{r.student_name}</Link>
                      <StatusBadge row={r} />
                    </div>
                    <p className="text-xs text-ink-secondary">{r.program} · {r.group ?? 'без группы'}</p>
                    <dl className="mt-2 grid grid-cols-2 gap-1 text-xs">
                      <dt className="text-ink-secondary">Стоимость</dt><dd>{r.contract_total ? som(r.contract_total) : '—'}</dd>
                      <dt className="text-ink-secondary">Получено</dt><dd>{som(r.received)}</dd>
                      <dt className="text-ink-secondary">Зачтено</dt><dd>{som(r.applied_to_studied)}</dd>
                      <dt className="text-ink-secondary">Остаток предоплаты</dt><dd className="font-semibold">{som(r.prepayment)}</dd>
                      <dt className="text-ink-secondary">Оплачено месяцев</dt><dd>{months(r)}</dd>
                    </dl>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Loadable>
      </div>
    </div>
  )
}
