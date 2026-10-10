import { Fragment, useState } from 'react'
import { FileDown, FileSpreadsheet } from 'lucide-react'
import { Link } from 'react-router-dom'

import { accountingApi } from '@/api/accounting'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { LoadingState } from '@/components/ui/LoadingState'
import { Pagination } from '@/components/ui/Pagination'
import { Select } from '@/components/ui/Select'
import { useAccountingOptions, useTeacherReport } from '@/hooks/useAccounting'
import type { AnalyticsFilters } from '@/types/accounting'

import { MonthFilters, currentMonth } from './AnalyticsPage'
import { PayrollStatusBadge, formatDate, som, useRunner } from './shared'

const PAGE_SIZE = 25

/**
 * Отчёт бухгалтера по сотрудникам за месяц: строки начислений (группа,
 * ученики, цена, процент, уроки) и итог каждого расчёта. Выплаты относятся к
 * расчёту целиком, поэтому «выплачено / остаток» — только в строке итога.
 */
export function ReportsPage() {
  const options = useAccountingOptions()
  const [filters, setFilters] = useState<AnalyticsFilters>(currentMonth)
  const [page, setPage] = useState(1)
  const report = useTeacherReport({ ...filters, page })
  const { run, busy } = useRunner()
  const change = (next: AnalyticsFilters) => { setFilters(next); setPage(1) }
  const r = report.data

  return (
    <div>
      <PageHeader
        title="Отчёт по сотрудникам"
        description={r ? `Месяц: ${r.range_label}. ${r.note}` : 'Начисления, выплаты и остатки за месяц'}
        actions={
          <div className="flex gap-2">
            <Button variant="secondary" leftIcon={<FileSpreadsheet className="size-4" />} isLoading={busy}
              onClick={() => run(() => accountingApi.downloadTeacherReport('xlsx', filters))}>XLSX</Button>
            <Button variant="secondary" leftIcon={<FileDown className="size-4" />} isLoading={busy}
              onClick={() => run(() => accountingApi.downloadTeacherReport('pdf', filters))}>PDF</Button>
          </div>
        }
      />
      <div className="flex flex-wrap gap-2">
        <MonthFilters value={filters} onChange={change} departments={options.data?.departments ?? []} />
        <FilterBar>
          <FilterField>
            <Select aria-label="Тип оплаты" value={filters.salary_type ?? ''} placeholder="Все типы оплаты" options={options.data?.salary_types ?? []}
              onChange={(e) => change({ ...filters, salary_type: e.target.value || undefined })} />
          </FilterField>
          <FilterField>
            <Select aria-label="Статус" value={filters.status ?? ''} placeholder="Все статусы" options={options.data?.payroll_statuses ?? []}
              onChange={(e) => change({ ...filters, status: e.target.value || undefined })} />
          </FilterField>
          <FilterField>
            <Select aria-label="Группа" value={filters.group ? String(filters.group) : ''} placeholder="Все группы"
              options={(options.data?.groups ?? []).map((g) => ({ value: String(g.id), label: g.name }))}
              onChange={(e) => change({ ...filters, group: Number(e.target.value) || undefined })} />
          </FilterField>
        </FilterBar>
      </div>

      {report.isLoading ? <LoadingState /> : report.isError || !r ? <ErrorState onRetry={() => report.refetch()} /> :
        r.results.length === 0 ? <EmptyState title="За выбранный месяц начислений нет" /> : (
          <>
            <div className="card overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Сотрудник</th><th>Направление</th><th>Группа</th><th>Период</th><th>Тип оплаты</th>
                    <th className="text-right">Учен.</th><th className="text-right">Цена</th><th className="text-right">%</th>
                    <th>Уроки</th><th className="text-right">Начислено</th><th className="text-right">Выплачено</th>
                    <th className="text-right">Остаток</th><th>План. выплата</th><th>Статус</th>
                  </tr>
                </thead>
                <tbody>
                  {r.results.map((p) => (
                    <Fragment key={p.payroll_id}>
                      {p.lines.map((l) => (
                        <tr key={l.line_id}>
                          <td>{p.employee_name}</td>
                          <td>{p.department_display}</td>
                          <td>{l.group_name || '—'}</td>
                          <td className="whitespace-nowrap">{p.period_label}</td>
                          <td className="text-xs">{p.salary_type_display}</td>
                          <td className="text-right">{l.students ?? '—'}</td>
                          <td className="text-right whitespace-nowrap">{l.price_per_student ? som(l.price_per_student) : '—'}</td>
                          <td className="text-right">{l.percentage ? `${Number(l.percentage)}%` : '—'}</td>
                          <td className="whitespace-nowrap">{l.lessons_done ? `${l.lessons_done}/${l.target_lessons}` : '—'}</td>
                          <td className="text-right whitespace-nowrap">{som(l.accrued)}</td>
                          <td /><td />
                          <td className="whitespace-nowrap">{formatDate(p.planned_payment_date)}</td>
                          <td />
                        </tr>
                      ))}
                      <tr className="bg-surface-muted font-medium">
                        <td colSpan={9}>
                          <Link className="text-brand-700 hover:underline" to={`/accounting/payrolls/${p.payroll_id}`}>Итого: {p.employee_name}</Link>
                          {Number(p.adjustments) ? <span className="ml-2 text-xs text-ink-muted">корректировки {som(p.adjustments)}</span> : null}
                        </td>
                        <td className="text-right whitespace-nowrap">{som(p.total)}</td>
                        <td className="text-right whitespace-nowrap">{som(p.paid)}</td>
                        <td className="text-right whitespace-nowrap">{som(p.due)}</td>
                        <td className="whitespace-nowrap">{formatDate(p.planned_payment_date)}</td>
                        <td><PayrollStatusBadge status={p.status} label={p.status_display} /></td>
                      </tr>
                    </Fragment>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="font-semibold">
                    <td colSpan={9}>Итого за месяц</td>
                    <td className="text-right whitespace-nowrap">{som(r.totals.total)}</td>
                    <td className="text-right whitespace-nowrap">{som(r.totals.paid)}</td>
                    <td className="text-right whitespace-nowrap">{som(r.totals.due)}</td>
                    <td colSpan={2} />
                  </tr>
                </tfoot>
              </table>
            </div>
            <div className="mt-4">
              <Pagination page={page} pageSize={PAGE_SIZE} totalCount={r.count} onPageChange={setPage} />
            </div>
            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <div className="card overflow-x-auto">
                <table className="data-table">
                  <thead><tr><th>Направление</th><th className="text-right">Начислено</th><th className="text-right">Выплачено</th><th className="text-right">Остаток</th></tr></thead>
                  <tbody>
                    {r.by_department.map((dep) => (
                      <tr key={dep.department}><td>{dep.label}</td><td className="text-right">{som(dep.accrued)}</td><td className="text-right">{som(dep.paid)}</td><td className="text-right">{som(dep.due)}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {r.by_group.length ? (
                <div className="card overflow-x-auto">
                  <table className="data-table">
                    <thead><tr><th>Группа</th><th className="text-right">Начислено</th></tr></thead>
                    <tbody>
                      {r.by_group.map((g) => <tr key={g.group_name}><td>{g.group_name}</td><td className="text-right">{som(g.accrued)}</td></tr>)}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </div>
          </>
        )}
    </div>
  )
}
