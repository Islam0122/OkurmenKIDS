import { Fragment, useState } from 'react'
import { FileDown, Wallet } from 'lucide-react'

import { accountingApi } from '@/api/accounting'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { LoadingState } from '@/components/ui/LoadingState'
import { Select } from '@/components/ui/Select'
import { StatCard } from '@/components/ui/StatCard'
import { StatGrid } from '@/components/ui/StatGrid'
import { useMySalary } from '@/hooks/useAccounting'
import type { MySalaryFilters, MySalaryRow, MySalaryStatus, PeriodType } from '@/types/accounting'

import { MONTHS, Section, formatDate, som, useRunner } from './shared'

const STATUS_TONE: Record<MySalaryStatus, BadgeTone> = {
  AWAITING: 'muted',
  CALCULATED: 'info',
  APPROVED: 'brand',
  PARTIALLY_PAID: 'warning',
  PAID: 'success',
}

const PERIOD_LABEL: Record<PeriodType, string> = {
  MONTH: 'Весь месяц (оклад)',
  FIRST_HALF: '1–15 число',
  SECOND_HALF: '16 – конец месяца',
}

function StatusBadge({ row }: { row: MySalaryRow }) {
  return <Badge tone={STATUS_TONE[row.status]}>{row.status_display}</Badge>
}

function rateText(rate: { amount: string | null; percentage: string | null; scope: string }): string {
  const value = rate.percentage !== null ? `${Number(rate.percentage)}% от стоимости курса` : `${som(rate.amount)} в месяц`
  return rate.scope ? `${value} (${rate.scope})` : value
}

/**
 * «Моя зарплата» — собственные начисления и выплаты сотрудника (Assistant,
 * Team Lead, Trainer). Только чтение: сервер всегда берёт сотрудника из
 * текущей сессии, ни один id в запрос не передаётся.
 */
export function MySalaryPage() {
  const [filters, setFilters] = useState<MySalaryFilters>({})
  const salary = useMySalary(filters)
  const { run, busy } = useRunner()
  const year = new Date().getFullYear()

  if (salary.isLoading) return <LoadingState label="Загружаем вашу зарплату…" />
  if (salary.isError || !salary.data) return <ErrorState onRetry={() => salary.refetch()} />
  const d = salary.data
  const filtered = Boolean(filters.year || filters.month || filters.period_type)

  return (
    <div>
      <PageHeader
        title="Моя зарплата"
        description={d.profile
          ? `${d.profile.position} · ${d.profile.salary_type_display}`
          : 'Зарплатный профиль ещё не настроен бухгалтерией.'}
        actions={
          <Button variant="secondary" leftIcon={<FileDown className="size-4" />} isLoading={busy}
            onClick={() => run(() => accountingApi.downloadMySalaryPdf(filters))}>
            Скачать PDF
          </Button>
        }
      />

      <StatGrid>
        <StatCard label="Начислено" value={som(d.totals.accrued)}
          hint={Number(d.totals.pending_approval) ? `ещё ${som(d.totals.pending_approval)} ожидает утверждения` : 'утверждённые начисления'} />
        <StatCard label="Выплачено" value={som(d.totals.paid)} />
        <StatCard label="Остаток к выплате" value={som(d.totals.due)} tone={Number(d.totals.due) > 0 ? 'warning' : 'default'} />
        <StatCard label="Последняя выплата" icon={Wallet}
          value={d.last_payment ? som(d.last_payment.amount) : '—'}
          hint={d.last_payment ? formatDate(d.last_payment.payment_date) : 'выплат ещё не было'} />
      </StatGrid>

      {d.profile ? (
        <Section title="Условия оплаты">
          <div className="card p-4 text-sm">
            <p><span className="text-ink-secondary">Тип оплаты:</span> <b>{d.profile.salary_type_display}</b></p>
            {d.profile.rates.length ? d.profile.rates.map((r) => (
              <p key={`${r.rule_type}-${r.effective_from}-${r.scope}`}>
                <span className="text-ink-secondary">{r.percentage !== null ? 'Процентная ставка' : 'Оклад'}:</span> <b>{rateText(r)}</b>
                <span className="text-ink-muted"> · с {formatDate(r.effective_from)}</span>
              </p>
            )) : <p className="text-ink-muted">Действующая ставка не указана.</p>}
          </div>
        </Section>
      ) : null}

      <Section title={`Текущий месяц: ${d.current_month.label}`}>
        <div className="grid gap-3 sm:grid-cols-2">
          {d.current_month.periods.map((row) => (
            <div key={row.period_type} className="card p-4">
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm text-ink-secondary">{PERIOD_LABEL[row.period_type]}</p>
                <StatusBadge row={row} />
              </div>
              <p className="mt-1 text-2xl font-semibold text-ink tabular-nums">{row.accrued !== null ? som(row.accrued) : '—'}</p>
              <p className="text-xs text-ink-muted">
                {row.accrued !== null ? `выплачено ${som(row.paid)} · остаток ${som(row.due)}` : 'начисление появится после расчёта бухгалтерией'}
              </p>
            </div>
          ))}
        </div>
      </Section>

      <Section title="История начислений">
        <FilterBar>
          <FilterField label="Год" htmlFor="ms-year">
            <Select id="ms-year" value={filters.year ? String(filters.year) : ''} placeholder="Все годы"
              options={[year - 2, year - 1, year].map((y) => ({ value: String(y), label: String(y) }))}
              onChange={(e) => setFilters({ ...filters, year: Number(e.target.value) || undefined })} />
          </FilterField>
          <FilterField label="Месяц" htmlFor="ms-month">
            <Select id="ms-month" value={filters.month ? String(filters.month) : ''} placeholder="Все месяцы"
              options={MONTHS.map((label, i) => ({ value: String(i + 1), label }))}
              onChange={(e) => setFilters({ ...filters, month: Number(e.target.value) || undefined })} />
          </FilterField>
          <FilterField label="Период" htmlFor="ms-half">
            <Select id="ms-half" value={filters.period_type ?? ''} placeholder="Оба периода"
              options={Object.entries(PERIOD_LABEL).map(([value, label]) => ({ value, label }))}
              onChange={(e) => setFilters({ ...filters, period_type: (e.target.value || undefined) as PeriodType | undefined })} />
          </FilterField>
        </FilterBar>
        {d.history.length === 0 ? (
          <EmptyState
            title={filtered ? 'За выбранный период начислений нет' : 'Начислений пока нет'}
            description={filtered ? 'Измените фильтры, чтобы увидеть другие периоды.'
              : 'Когда бухгалтерия рассчитает вашу зарплату, начисления появятся здесь.'}
          />
        ) : <HistoryTable rows={d.history} />}
      </Section>

      <Section title="Выплаты">
        {d.payments.length === 0 ? <p className="text-sm text-ink-muted">Выплат пока не было.</p> : (
          <div className="card overflow-x-auto">
            <table className="data-table">
              <thead><tr><th>Дата</th><th>За период</th><th>Способ</th><th className="text-right">Сумма</th></tr></thead>
              <tbody>
                {d.payments.map((p) => (
                  <tr key={p.id}>
                    <td>{formatDate(p.payment_date)}{p.is_advance ? <Badge className="ml-2" tone="info">аванс</Badge> : null}</td>
                    <td>{p.period_label}</td>
                    <td>{p.method}</td>
                    <td className="text-right font-medium">{som(p.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </div>
  )
}

function HistoryTable({ rows }: { rows: MySalaryRow[] }) {
  const [open, setOpen] = useState<number | null>(null)
  return (
    <div className="card overflow-x-auto">
      <table className="data-table">
        <thead>
          <tr><th>Период</th><th>Статус</th><th className="text-right">Начислено</th><th className="text-right">Выплачено</th><th className="text-right">Остаток</th></tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const key = row.payroll_id ?? 0
            const details = row.lines.length + row.adjustments.length > 0
            return (
              <Fragment key={key}>
                <tr onClick={details ? () => setOpen(open === key ? null : key) : undefined} className={details ? 'cursor-pointer' : undefined}>
                  <td>
                    {row.period_label}
                    {details ? <p className="text-xs text-ink-muted">{open === key ? 'скрыть' : 'показать'} детализацию</p> : null}
                  </td>
                  <td><StatusBadge row={row} /></td>
                  <td className="text-right">{som(row.accrued)}</td>
                  <td className="text-right">{som(row.paid)}</td>
                  <td className="text-right">{som(row.due)}</td>
                </tr>
                {open === key ? (
                  <tr>
                    <td colSpan={5} className="bg-surface-muted text-sm">
                      <ul className="space-y-1">
                        {row.lines.map((l) => (
                          <li key={l.description} className="flex justify-between gap-3"><span>{l.description}</span><span className="whitespace-nowrap">{som(l.amount)}</span></li>
                        ))}
                        {row.adjustments.map((a) => (
                          <li key={`${a.kind}-${a.reason}`} className="flex justify-between gap-3 text-ink-secondary">
                            <span>{a.kind}: {a.reason}</span><span className="whitespace-nowrap">{som(a.amount)}</span>
                          </li>
                        ))}
                      </ul>
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
