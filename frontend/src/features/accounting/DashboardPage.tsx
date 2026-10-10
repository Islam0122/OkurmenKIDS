import { useMemo, useState } from 'react'
import { AlertTriangle, Calculator, CheckCheck, FileDown, FileSpreadsheet, Users } from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { accountingApi } from '@/api/accounting'
import type { PayrollFilters } from '@/api/accounting'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { DataTable } from '@/components/ui/DataTable'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { LoadingState } from '@/components/ui/LoadingState'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { StatCard } from '@/components/ui/StatCard'
import { StatGrid } from '@/components/ui/StatGrid'
import { useToast } from '@/components/ui/Toast'
import { useAccountingDashboard, useAccountingEmployees, useAccountingOptions } from '@/hooks/useAccounting'
import { useQueryClient } from '@tanstack/react-query'
import type { CalculationResult, EmployeeRow, PeriodSelection } from '@/types/accounting'

import { Notice, PayrollStatusBadge, PeriodPicker, Section, currentSelection, som, useRunner } from './shared'

function readSelection(params: URLSearchParams): PeriodSelection {
  const fallback = currentSelection()
  const half = params.get('half')
  return {
    year: Number(params.get('year')) || fallback.year,
    month: Number(params.get('month')) || fallback.month,
    half: half === 'FIRST_HALF' || half === 'SECOND_HALF' || half === 'MONTH' ? half : fallback.half,
  }
}

const RATE_SUFFIX: Record<string, string> = {
  FIXED: 'оклад',
  PER_STUDENT: 'за студента',
  PER_GROUP: 'за группу',
  BONUS: 'бонус',
  REVENUE_PERCENT: 'от оплат',
}

function rateLabel(row: EmployeeRow): string {
  if (row.rates.length === 0) return 'не настроена'
  return row.rates
    .map((r) => {
      const value = r.percentage !== null ? `${Number(r.percentage)}%` : som(r.amount)
      return `${value} ${RATE_SUFFIX[r.rule_type] ?? ''}${r.scope ? ` (${r.scope})` : ''}`
    })
    .join('; ')
}

export function AccountingDashboardPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [params, setParams] = useSearchParams()
  const selection = readSelection(params)
  const [filters, setFilters] = useState<PayrollFilters & { payment_status?: string }>({})
  const [result, setResult] = useState<CalculationResult | null>(null)
  const { run, busy } = useRunner()
  const { showToast } = useToast()

  const options = useAccountingOptions()
  const dashboard = useAccountingDashboard(selection)
  const employees = useAccountingEmployees(selection, filters)
  const isHalf = selection.half !== 'MONTH'
  const period = dashboard.data?.periods.find((p) => p.period_type === selection.half)

  const setSelection = (next: PeriodSelection) => {
    setResult(null)
    setParams({ year: String(next.year), month: String(next.month), half: next.half }, { replace: true })
  }
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['accounting'] })

  const calculate = () =>
    run(async () => {
      if (selection.half === 'MONTH') return
      const p = await accountingApi.ensurePeriod(selection.year, selection.month, selection.half)
      setResult(await accountingApi.calculatePeriod(p.id))
      await refresh()
    }, 'Расчёт выполнен')

  const approveAll = () =>
    run(async () => {
      if (!period) return
      const r = await accountingApi.approvePeriod(period.id)
      await refresh()
      showToast(`Утверждено: ${r.approved.length}`, 'success')
      if (r.failed.length) showToast(`Не утверждены — ${r.failed.map((f) => `${f.employee}: ${f.error}`).join('; ')}`, 'error')
    })

  const opts = options.data
  const groupOptions = useMemo(
    () => (opts?.groups ?? []).filter((g) => !filters.program || g.course === filters.program).map((g) => ({ value: String(g.id), label: g.name })),
    [opts, filters.program],
  )

  const d = dashboard.data
  return (
    <div>
      <PageHeader
        title="Начисления и выплаты"
        description={d?.range_label ? `Период: ${d.range_label}` : 'Расчёт зарплат два раза в месяц'}
        actions={<PeriodPicker value={selection} onChange={setSelection} />}
      />

      {dashboard.isError ? <ErrorState onRetry={() => dashboard.refetch()} /> : null}
      {d ? (
        <StatGrid>
          <StatCard label="Начислено" value={som(d.total_accrued)}
            hint={Number(d.total_adjustments) ? `в т.ч. корректировки ${som(d.total_adjustments)}` : undefined} />
          <StatCard label="Выплачено" value={som(d.total_paid)} />
          <StatCard label="Задолженность" value={som(d.total_due)}
            tone={Number(d.total_due) > 0 ? 'warning' : 'default'}
            hint={`Всего по утверждённым: ${som(d.outstanding_debt_all_periods)}`} />
          <StatCard label="Сотрудников с начислениями" value={d.employees_with_accruals} icon={Users}
            hint={`Ждут утверждения: ${d.pending_approval}${d.pending_adjustments ? ` · корректировок: ${d.pending_adjustments}` : ''}`}
            tone={d.pending_approval ? 'warning' : 'default'} />
        </StatGrid>
      ) : dashboard.isLoading ? <LoadingState /> : null}

      <div className="mt-4 flex flex-wrap gap-2">
        {opts?.can_operate ? (
          <Button leftIcon={<Calculator className="size-4" />} isLoading={busy} disabled={!isHalf || period?.status === 'CLOSED'}
            onClick={calculate} title={isHalf ? undefined : 'Выберите половину месяца'}>
            Рассчитать зарплаты
          </Button>
        ) : null}
        {opts?.can_approve ? (
          <Button variant="secondary" leftIcon={<CheckCheck className="size-4" />} isLoading={busy}
            disabled={!period || !d?.pending_approval} onClick={approveAll}>
            Утвердить все без ошибок
          </Button>
        ) : null}
        <Button variant="ghost" leftIcon={<FileDown className="size-4" />}
          onClick={() => run(() => accountingApi.downloadReport('pdf', selection, filters))}>
          PDF
        </Button>
        <Button variant="ghost" leftIcon={<FileSpreadsheet className="size-4" />}
          onClick={() => run(() => accountingApi.downloadReport('xlsx', selection, filters))}>
          Excel
        </Button>
        {period ? <span className="self-center text-sm text-ink-muted">Статус периода: {period.status_display}</span> : null}
      </div>

      {result ? <CalculationSummary result={result} onOpen={(id) => navigate(`/accounting/payrolls/${id}`)} /> : null}

      <Section title="Сотрудники">
        <FilterBar>
          <FilterField size="lg">
            <SearchInput value={filters.search ?? ''} placeholder="Поиск по ФИО"
              onChange={(value: string) => setFilters({ ...filters, search: value || undefined })} />
          </FilterField>
          <FilterField>
            <Select aria-label="Тип оплаты" value={filters.salary_type ?? ''} placeholder="Все типы оплаты"
              options={opts?.salary_types ?? []}
              onChange={(e) => setFilters({ ...filters, salary_type: e.target.value || undefined })} />
          </FilterField>
          <FilterField>
            <Select aria-label="Статус" value={filters.payment_status ?? ''} placeholder="Все статусы"
              options={opts?.payroll_statuses ?? []}
              onChange={(e) => setFilters({ ...filters, payment_status: e.target.value || undefined })} />
          </FilterField>
          <FilterField>
            <Select aria-label="Программа" value={filters.program ? String(filters.program) : ''} placeholder="Все программы"
              options={(opts?.courses ?? []).map((c) => ({ value: String(c.id), label: c.name }))}
              onChange={(e) => setFilters({ ...filters, program: Number(e.target.value) || undefined, group: undefined })} />
          </FilterField>
          <FilterField>
            <Select aria-label="Группа" value={filters.group ? String(filters.group) : ''} placeholder="Все группы"
              options={groupOptions}
              onChange={(e) => setFilters({ ...filters, group: Number(e.target.value) || undefined })} />
          </FilterField>
        </FilterBar>

        {employees.isLoading ? <LoadingState /> : employees.isError ? (
          <ErrorState onRetry={() => employees.refetch()} />
        ) : (employees.data?.results.length ?? 0) === 0 ? (
          <EmptyState title="Нет сотрудников" description="Добавьте зарплатные профили в разделе «Зарплатные правила»." />
        ) : (
          <DataTable<EmployeeRow>
            rows={employees.data!.results}
            getRowKey={(row) => row.profile_id}
            onRowClick={(row) => (row.payroll_id ? navigate(`/accounting/payrolls/${row.payroll_id}`) : undefined)}
            columns={[
              { key: 'name', header: 'ФИО', render: (r) => <span className="font-medium text-ink">{r.employee_name}</span> },
              { key: 'position', header: 'Должность', render: (r) => r.position },
              { key: 'type', header: 'Тип оплаты', render: (r) => r.salary_type_display },
              { key: 'rate', header: 'Оклад / ставка', render: (r) => <span className="text-xs">{rateLabel(r)}</span> },
              { key: 'students', header: 'Активные студенты', render: (r) => r.active_students ?? '—' },
              { key: 'accrued', header: 'Начислено', className: 'text-right', render: (r) => som(r.accrued) },
              { key: 'paid', header: 'Выплачено', className: 'text-right', render: (r) => som(r.paid) },
              { key: 'due', header: 'Остаток', className: 'text-right', render: (r) => som(r.due) },
              { key: 'status', header: 'Статус', render: (r) => <PayrollStatusBadge status={r.status} label={r.status_display} /> },
            ]}
          />
        )}
      </Section>
    </div>
  )
}

function CalculationSummary({ result, onOpen }: { result: CalculationResult; onOpen: (id: number) => void }) {
  const withIssues = result.calculated.filter((p) => p.errors.length || p.warnings.length)
  return (
    <Card className="mt-4" title="Предварительная таблица расчёта"
      description={`Рассчитано: ${result.calculated.length} · пропущено (уже утверждены): ${result.skipped.length} · ошибок: ${result.failed.length}`}>
      {result.failed.length ? (
        <Notice tone="danger" items={result.failed.map((f) => `${f.employee}: ${f.error}`)} />
      ) : null}
      <div className="mt-3 overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr><th>Сотрудник</th><th className="text-right">Начислено</th><th>Предупреждения и ошибки</th></tr>
          </thead>
          <tbody>
            {result.calculated.map((p) => (
              <tr key={p.id} onClick={() => onOpen(p.id)} className="cursor-pointer">
                <td className="font-medium">{p.employee_name}</td>
                <td className="text-right">{som(p.total)}</td>
                <td className="text-xs">
                  {p.errors.map((e) => <p key={e} className="text-danger">✕ {e}</p>)}
                  {p.warnings.map((w) => <p key={w} className="text-warning">⚠ {w}</p>)}
                  {!p.errors.length && !p.warnings.length ? <span className="text-ink-muted">—</span> : null}
                </td>
              </tr>
            ))}
            {result.skipped.map((s) => (
              <tr key={`s-${s.payroll_id}`} onClick={() => onOpen(s.payroll_id)} className="cursor-pointer">
                <td>{s.employee}</td><td className="text-right">—</td><td className="text-xs text-ink-muted">{s.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {withIssues.length ? (
        <p className="mt-3 flex items-center gap-1.5 text-sm text-warning">
          <AlertTriangle className="size-4" aria-hidden /> Проверьте сотрудников с предупреждениями перед утверждением.
        </p>
      ) : null}
    </Card>
  )
}
