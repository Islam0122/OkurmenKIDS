import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'

import { financeApi } from '@/api/finance'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { DataTable } from '@/components/ui/DataTable'
import { DatePicker } from '@/components/ui/DatePicker'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { Input } from '@/components/ui/Input'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import type { ArchiveFilters, ArchiveRow, ArchiveStatistics } from '@/types/finance'

import { Amount, FINANCE_KEY, Loadable, Stat, formatDate, som, useFinanceOptions } from './ui'

const PAGE_SIZE = 25

/** Фильтры архива живут в URL: открыли карточку, вернулись «Назад» — тот же список. */
function useArchiveFilters(): [ArchiveFilters, (next: ArchiveFilters) => void] {
  const [params, setParams] = useSearchParams()
  const text = (key: string) => params.get(key) || undefined
  const num = (key: string) => (params.get(key) ? Number(params.get(key)) : undefined)
  const debt = params.get('debt')
  const filters: ArchiveFilters = {
    search: text('search'), contract: text('contract'), group: num('group'), subject: num('subject'),
    reason: text('reason'), debt: debt === 'yes' || debt === 'no' ? debt : undefined,
    date_from: text('date_from'), date_to: text('date_to'), page: num('page') ?? 1,
  }
  const set = (next: ArchiveFilters) => {
    const out = new URLSearchParams()
    for (const [key, value] of Object.entries(next)) {
      if (value !== undefined && value !== null && value !== '' && !(key === 'page' && value === 1)) out.set(key, String(value))
    }
    setParams(out, { replace: true })
  }
  return [filters, set]
}

function Kpis({ stats }: { stats: ArchiveStatistics }) {
  return (
    <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
      <Stat label="Деактивировано" value={stats.total} hint="студентов в архиве" />
      <Stat label="Долг архива" value={som(stats.debt_total)} tone={Number(stats.debt_total) > 0 ? 'danger' : undefined}
        hint="сумма задолженности" />
      <Stat label="С долгом" value={stats.with_debt} tone={stats.with_debt ? 'warning' : undefined} hint="студентов" />
      <Stat label="Без задолженности" value={stats.without_debt} hint="студентов" />
      <Stat label="Получено платежей" value={som(stats.paid_total)} tone="brand"
        hint={Number(stats.overpayment_total) > 0 ? `переплата ${som(stats.overpayment_total)}` : 'за вычетом возвратов'} />
    </div>
  )
}

function Filters({ filters, onChange }: { filters: ArchiveFilters; onChange: (f: ArchiveFilters) => void }) {
  const options = useFinanceOptions()
  const set = (patch: Partial<ArchiveFilters>) => onChange({ ...filters, ...patch, page: 1 })
  const num = (v: string) => (v ? Number(v) : undefined)
  return (
    <FilterBar>
      <FilterField size="lg">
        <SearchInput value={filters.search ?? ''} placeholder="ФИО или телефон" onChange={(v) => set({ search: v || undefined })} />
      </FilterField>
      <FilterField>
        <Input aria-label="Номер договора" placeholder="№ договора / начисления" value={filters.contract ?? ''}
          onChange={(e) => set({ contract: e.target.value || undefined })} />
      </FilterField>
      <FilterField>
        <Select aria-label="Группа" value={filters.group ? String(filters.group) : ''} placeholder="Все группы"
          options={(options.data?.groups ?? []).map((g) => ({ value: String(g.id), label: g.name }))}
          onChange={(e) => set({ group: num(e.target.value) })} />
      </FilterField>
      <FilterField>
        <Select aria-label="Направление" value={filters.subject ? String(filters.subject) : ''} placeholder="Все направления"
          options={(options.data?.subjects ?? []).map((s) => ({ value: String(s.id), label: s.name }))}
          onChange={(e) => set({ subject: num(e.target.value) })} />
      </FilterField>
      <FilterField>
        <Select aria-label="Причина деактивации" value={filters.reason ?? ''} placeholder="Все причины"
          options={options.data?.deactivation_reasons ?? []} onChange={(e) => set({ reason: e.target.value || undefined })} />
      </FilterField>
      <FilterField>
        <Select aria-label="Задолженность" value={filters.debt ?? ''} placeholder="Долг: все"
          options={[{ value: 'yes', label: 'С долгом' }, { value: 'no', label: 'Без долга' }]}
          onChange={(e) => set({ debt: (e.target.value || undefined) as ArchiveFilters['debt'] })} />
      </FilterField>
      <FilterField label="Деактивирован с" htmlFor="archive-from">
        <DatePicker id="archive-from" value={filters.date_from ?? ''} onChange={(e) => set({ date_from: e.target.value || undefined })} />
      </FilterField>
      <FilterField label="по" htmlFor="archive-to">
        <DatePicker id="archive-to" value={filters.date_to ?? ''} onChange={(e) => set({ date_to: e.target.value || undefined })} />
      </FilterField>
    </FilterBar>
  )
}

/** «Архив студентов»: деактивированные в LMS студенты появляются здесь сами — бухгалтеру
 * ничего не нужно добавлять вручную. Деньги — те же, что в карточке договора. */
export function ArchivePage() {
  const navigate = useNavigate()
  const location = useLocation()
  const [filters, setFilters] = useArchiveFilters()
  const query = useQuery({
    queryKey: [...FINANCE_KEY, 'archive', filters],
    queryFn: () => financeApi.archive({ ...filters, page_size: PAGE_SIZE }),
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: true,
  })
  const filtered = Object.entries(filters).some(([k, v]) => k !== 'page' && v !== undefined)

  return (
    <div>
      <PageHeader title="Архив студентов"
        description="Деактивированные студенты: долг, оплаты и история сохраняются. Оплату старого долга можно принять в карточке." />
      {query.data ? <Kpis stats={query.data.statistics} /> : null}
      <Filters filters={filters} onChange={setFilters} />
      <div className="mt-4">
        <Loadable query={query} empty={(d) => d.count === 0}
          emptyTitle={filtered ? 'Никого не найдено' : 'Архив пуст'}
          emptyDescription={filtered ? 'Измените фильтры.' : 'Студенты появятся здесь, когда их деактивируют в LMS.'}>
          {(data) => (
            <>
              <DataTable<ArchiveRow>
                rows={data.results} getRowKey={(r) => r.id}
                onRowClick={(r) => navigate(`/finance/archive/${r.id}`, { state: { from: location.pathname + location.search } })}
                columns={[
                  { key: 'id', header: '№', render: (r) => <span className="tabular-nums text-ink-secondary">{r.id}</span> },
                  { key: 'name', header: 'Студент', render: (r) => <span className="font-medium text-ink">{r.name}</span> },
                  { key: 'group', header: 'Группа', render: (r) => r.group?.name ?? '—' },
                  { key: 'subject', header: 'Направление', render: (r) => r.subjects.join(', ') || '—' },
                  { key: 'contract', header: 'Договор', render: (r) => (
                    <div>
                      <Amount value={r.finance.contract_price} />
                      <p className="text-xs text-ink-secondary">
                        {r.contracts.length ? r.contracts.map((c) => `№${c.number}`).join(', ') : 'без договора'}
                      </p>
                    </div>
                  ) },
                  { key: 'invoiced', header: 'Начислено', render: (r) => <Amount value={r.finance.invoiced} /> },
                  { key: 'paid', header: 'Оплачено', render: (r) => <Amount value={r.finance.paid} /> },
                  { key: 'discount', header: 'Скидка', render: (r) => <Amount value={r.finance.discount} tone="muted" /> },
                  { key: 'debt', header: 'Долг', render: (r) => (
                    <div>
                      <Amount value={r.finance.debt} tone={r.finance.has_debt ? 'danger' : 'muted'} />
                      {Number(r.finance.overpayment) > 0
                        ? <p className="text-xs text-brand-700">переплата {som(r.finance.overpayment)}</p> : null}
                    </div>
                  ) },
                  { key: 'date', header: 'Дата деактивации', render: (r) => <span className="whitespace-nowrap">{formatDate(r.deactivated_on)}</span> },
                  { key: 'reason', header: 'Причина', render: (r) => <span className="text-sm">{r.reason_display}</span> },
                  { key: 'status', header: 'Статус', render: (r) => <Badge tone="muted">{r.status_display}</Badge> },
                ]}
              />
              <div className="mt-3">
                <Pagination page={data.page} pageSize={data.page_size} totalCount={data.count}
                  onPageChange={(page) => setFilters({ ...filters, page })} />
              </div>
            </>
          )}
        </Loadable>
      </div>
    </div>
  )
}
