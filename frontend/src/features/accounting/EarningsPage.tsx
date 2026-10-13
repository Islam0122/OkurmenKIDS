import { Fragment, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronRight } from 'lucide-react'

import { accountingApi } from '@/api/accounting'
import { PageHeader } from '@/components/layout/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { LoadingState } from '@/components/ui/LoadingState'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { useAccountingOptions } from '@/hooks/useAccounting'

import { EarningsBreakdown } from './EarningsBreakdown'
import { formatDate, som } from './shared'

/** Заработок сотрудников на текущую дату — тот же расчёт, что сотрудник видит
 * в «Моей зарплате». Только просмотр: ничего не начисляет и не выплачивает. */
export function EarningsPage() {
  const options = useAccountingOptions()
  const [filters, setFilters] = useState<{ search?: string; department?: string }>({})
  const [open, setOpen] = useState<number | null>(null)
  const list = useQuery({
    queryKey: ['accounting', 'earnings', filters],
    queryFn: () => accountingApi.earnings(filters),
  })
  return (
    <div>
      <PageHeader
        title="Заработок сотрудников"
        description="Сколько сотрудник заработал на сегодня по проведённым урокам и правилам оплаты, сколько начислено официально и сколько компания должна выплатить. Заработок по незавершённым блокам не является начислением и в план выплат не попадает."
      />
      <FilterBar>
        <FilterField size="lg">
          <SearchInput value={filters.search ?? ''} placeholder="Поиск по ФИО" onChange={(v) => setFilters({ ...filters, search: v || undefined })} />
        </FilterField>
        <FilterField>
          <Select aria-label="Направление" value={filters.department ?? ''} placeholder="Все направления" options={options.data?.departments ?? []}
            onChange={(e) => setFilters({ ...filters, department: e.target.value || undefined })} />
        </FilterField>
      </FilterBar>
      {list.isLoading ? <LoadingState /> : list.isError ? <ErrorState onRetry={() => list.refetch()} /> :
        !list.data?.results.length ? <EmptyState title="Сотрудников с зарплатным профилем нет" /> : (
          <div className="card overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th /><th>Сотрудник</th><th className="text-right">Заработано</th><th className="text-right">Налог и удержания</th>
                  <th className="text-right">На руки</th><th className="text-right">Начислено официально</th><th className="text-right">Выплачено</th>
                  <th className="text-right">Остаток обязательств</th><th>Выплата</th>
                </tr>
              </thead>
              <tbody>
                {list.data.results.map((r) => (
                  <Fragment key={r.employee}>
                    <tr className="cursor-pointer hover:bg-surface-hover" onClick={() => setOpen(open === r.employee ? null : r.employee)}>
                      <td>{open === r.employee ? <ChevronDown className="size-4" aria-hidden /> : <ChevronRight className="size-4" aria-hidden />}</td>
                      <td>{r.employee_name}<p className="text-xs text-ink-muted">{r.position} · {r.salary_type_display}</p></td>
                      <td className="whitespace-nowrap text-right">
                        {som(r.earned.gross)}
                        {Number(r.difference) !== 0 ? <p className="text-xs text-ink-muted">вне начисления {som(r.difference)}</p> : null}
                      </td>
                      <td className="whitespace-nowrap text-right">{som((Number(r.earned.tax) + Number(r.earned.other_deductions)).toFixed(2))}</td>
                      <td className="whitespace-nowrap text-right">{som(r.earned.net)}</td>
                      <td className="whitespace-nowrap text-right">{som(r.official.gross)}</td>
                      <td className="whitespace-nowrap text-right">{som(r.paid)}</td>
                      <td className={`whitespace-nowrap text-right ${Number(r.company_owes) > 0 ? 'text-warning' : ''}`}>{som(r.company_owes)}</td>
                      <td className="whitespace-nowrap text-sm">{r.next_payment_date ? formatDate(r.next_payment_date) : '—'}</td>
                    </tr>
                    {open === r.employee ? (
                      <tr><td /><td colSpan={8} className="bg-surface-muted"><EmployeeDetail id={r.employee} /></td></tr>
                    ) : null}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </div>
  )
}

function EmployeeDetail({ id }: { id: number }) {
  const detail = useQuery({ queryKey: ['accounting', 'earnings', 'employee', id], queryFn: () => accountingApi.employeeEarnings(id) })
  if (detail.isLoading) return <LoadingState />
  if (detail.isError || !detail.data) return <ErrorState onRetry={() => detail.refetch()} />
  const d = detail.data
  return (
    <div className="py-2">
      <p className="mb-2 text-sm text-ink-secondary">
        Налог {som(d.earned.tax)} · другие удержания {som(d.earned.other_deductions)} · заработано, но не выплачено {som(d.earned_unpaid)}
        {' '}· официальные удержания {som((Number(d.official.tax) + Number(d.official.other_deductions)).toFixed(2))}
      </p>
      <EarningsBreakdown data={d} />
    </div>
  )
}
