import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, CalendarClock, CheckCircle2, ClipboardList, Plus, Users, Wallet } from 'lucide-react'

import { accountingApi } from '@/api/accounting'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { Pagination } from '@/components/ui/Pagination'
import { Select } from '@/components/ui/Select'
import { StatCard } from '@/components/ui/StatCard'
import { StatGrid } from '@/components/ui/StatGrid'
import { Tabs } from '@/components/ui/Tabs'
import { Textarea } from '@/components/ui/Textarea'
import { Field } from '@/features/worklog/formUi'
import {
  useAccountingMutation,
  useAccountingOptions,
  usePayoutCalendar,
  usePayoutCandidates,
  usePayoutPlans,
  usePayoutSummary,
} from '@/hooks/useAccounting'
import type { PayoutCandidate, PayoutPlanDetail, PayoutPlanFilters, PayoutPlanStatus } from '@/types/accounting'

import { MONTHS, formatDate, som, useRunner } from './shared'

const PAGE_SIZE = 50

export const PAYOUT_STATUSES: { value: PayoutPlanStatus; label: string }[] = [
  { value: 'DRAFT', label: 'Черновик' },
  { value: 'SCHEDULED', label: 'Запланировано' },
  { value: 'PARTIALLY_FUNDED', label: 'Частично профинансировано' },
  { value: 'READY', label: 'Готово к выплате' },
  { value: 'PARTIALLY_PAID', label: 'Частично выплачено' },
  { value: 'PAID', label: 'Выплачено' },
  { value: 'CANCELLED', label: 'Отменено' },
]

const STATUS_TONE: Record<PayoutPlanStatus, BadgeTone> = {
  DRAFT: 'muted',
  SCHEDULED: 'info',
  PARTIALLY_FUNDED: 'warning',
  READY: 'brand',
  PARTIALLY_PAID: 'warning',
  PAID: 'success',
  CANCELLED: 'muted',
}

export function PayoutStatusBadge({ status, label }: { status: PayoutPlanStatus; label: string }) {
  return <Badge tone={STATUS_TONE[status]}>{label}</Badge>
}

export function Readiness({ percent }: { percent: string }) {
  const value = Math.min(100, Math.max(0, Number(percent)))
  return (
    <div className="flex items-center gap-2" title={`Готовность ${percent}%`}>
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-surface-muted" aria-hidden>
        <div className={value >= 100 ? 'h-full bg-success' : 'h-full bg-warning'} style={{ width: `${value}%` }} />
      </div>
      <span className="text-xs text-ink-secondary">{percent}%</span>
    </div>
  )
}

const thisYear = new Date().getFullYear()
const YEARS = [thisYear - 1, thisYear, thisYear + 1].map((y) => ({ value: String(y), label: String(y) }))

export function PayoutPlanPage() {
  const navigate = useNavigate()
  const options = useAccountingOptions()
  const [filters, setFilters] = useState<PayoutPlanFilters>({ year: thisYear })
  const [tab, setTab] = useState<'plans' | 'calendar'>('plans')
  const [creating, setCreating] = useState<{ payout_date?: string } | null>(null)
  const plans = usePayoutPlans(filters)
  const summary = usePayoutSummary(filters)
  const calendar = usePayoutCalendar(filters, tab === 'calendar')
  const canEdit = options.data?.can_operate ?? false
  const set = (patch: Partial<PayoutPlanFilters>) => setFilters({ ...filters, ...patch, page: undefined })
  const s = summary.data

  return (
    <div>
      <PageHeader
        title="План выплат"
        description="Подготовка выплат на дату по утверждённым начислениям. Подготовленные средства — не выплата: фактические выплаты регистрируются отдельно и сразу уменьшают остаток."
        actions={canEdit ? <Button leftIcon={<Plus className="size-4" />} onClick={() => setCreating({})}>Создать план</Button> : null}
      />

      <FilterBar>
        <FilterField>
          <Select aria-label="Месяц начислений" value={filters.month ? String(filters.month) : ''} placeholder="Все месяцы"
            options={MONTHS.map((label, i) => ({ value: String(i + 1), label }))}
            onChange={(e) => set({ month: Number(e.target.value) || undefined })} />
        </FilterField>
        <FilterField>
          <Select aria-label="Год" value={filters.year ? String(filters.year) : ''} placeholder="Все годы" options={YEARS}
            onChange={(e) => set({ year: Number(e.target.value) || undefined })} />
        </FilterField>
        <FilterField label="Дата выплаты" htmlFor="pp-date">
          <Input id="pp-date" type="date" value={filters.payout_date ?? ''} onChange={(e) => set({ payout_date: e.target.value || undefined })} />
        </FilterField>
        <FilterField>
          <Select aria-label="Статус плана" value={filters.status ?? ''} placeholder="Все статусы" options={PAYOUT_STATUSES}
            onChange={(e) => set({ status: e.target.value || undefined })} />
        </FilterField>
        <FilterField>
          <Select aria-label="Отдел" value={filters.department ?? ''} placeholder="Все отделы" options={options.data?.departments ?? []}
            onChange={(e) => set({ department: e.target.value || undefined })} />
        </FilterField>
        <FilterField>
          <Select aria-label="Сотрудник" value={filters.employee ? String(filters.employee) : ''} placeholder="Все сотрудники"
            options={(options.data?.employees ?? []).map((e) => ({ value: String(e.id), label: e.full_name }))}
            onChange={(e) => set({ employee: Number(e.target.value) || undefined })} />
        </FilterField>
      </FilterBar>

      {s ? (
        <StatGrid columns={3} className="mb-6">
          <StatCard label="Всего запланировано" value={som(s.planned)} icon={ClipboardList}
            hint={`Планов: ${s.plans} · осталось выплатить ${som(s.to_pay)}`} />
          <StatCard label="Подготовлено средств" value={som(s.prepared)} icon={Wallet} hint={`Готовность ${s.readiness_percent}%`} />
          <StatCard label="Дефицит" value={som(s.deficit)} icon={AlertTriangle} tone={Number(s.deficit) > 0 ? 'danger' : 'default'}
            hint="Не хватает до суммы к выплате" />
          <StatCard label="Сотрудников к выплате" value={s.employees} icon={Users} />
          <StatCard label="Уже выплачено по планам" value={som(s.paid)} icon={CheckCircle2} />
          <StatCard label="Остаток обязательств" value={som(s.remaining_obligations)} icon={CalendarClock}
            tone={Number(s.remaining_obligations) > 0 ? 'warning' : 'default'} hint="Невыплаченный остаток начислений в планах" />
        </StatGrid>
      ) : null}

      <Tabs aria-label="Вид" value={tab} onChange={setTab}
        items={[{ key: 'plans', label: 'Планы' }, { key: 'calendar', label: 'Календарь выплат' }]} />

      {tab === 'plans' ? (
        plans.isLoading ? <LoadingState /> : plans.isError ? <ErrorState onRetry={() => plans.refetch()} /> :
          !plans.data?.results.length ? (
            <EmptyState title="Планов выплат нет" description={canEdit ? 'Создайте план на дату выплаты и включите в него утверждённые начисления.' : undefined} />
          ) : (
            <>
              <div className="card overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Дата</th><th>Название</th><th className="text-right">Сотрудники</th><th className="text-right">План</th>
                      <th className="text-right">Подготовлено</th><th className="text-right">Дефицит</th><th>Статус</th>
                    </tr>
                  </thead>
                  <tbody>
                    {plans.data.results.map((p) => (
                      <tr key={p.id} className="cursor-pointer hover:bg-surface-hover" onClick={() => navigate(`/accounting/payout-plan/${p.id}`)}>
                        <td className="whitespace-nowrap">{formatDate(p.payout_date)}</td>
                        <td>
                          <a href={`/accounting/payout-plan/${p.id}`} className="font-medium text-ink hover:text-brand-700"
                            onClick={(e) => { e.preventDefault(); navigate(`/accounting/payout-plan/${p.id}`) }}>{p.title}</a>
                          <p className="text-xs text-ink-muted">начисления за {MONTHS[p.month - 1].toLowerCase()} {p.year}</p>
                        </td>
                        <td className="text-right">{p.totals.employees}</td>
                        <td className="whitespace-nowrap text-right">
                          {som(p.totals.planned)}
                          {Number(p.totals.paid) > 0 ? <p className="text-xs text-ink-muted">выплачено {som(p.totals.paid)}</p> : null}
                        </td>
                        <td className="whitespace-nowrap text-right">{som(p.totals.prepared)}</td>
                        <td className={`whitespace-nowrap text-right ${Number(p.totals.deficit) > 0 && p.totals.status !== 'CANCELLED' ? 'text-danger' : ''}`}>
                          {p.totals.status === 'CANCELLED' ? '—' : som(p.totals.deficit)}
                        </td>
                        <td>
                          <PayoutStatusBadge status={p.totals.status} label={p.totals.status_display} />
                          {p.totals.status !== 'CANCELLED' && p.totals.status !== 'DRAFT' && p.totals.status !== 'PAID'
                            ? <div className="mt-1"><Readiness percent={p.totals.readiness_percent} /></div> : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="mt-4">
                <Pagination page={filters.page ?? 1} pageSize={PAGE_SIZE} totalCount={plans.data.count}
                  onPageChange={(page) => setFilters({ ...filters, page })} />
              </div>
            </>
          )
      ) : calendar.isLoading ? <LoadingState /> : calendar.isError ? <ErrorState onRetry={() => calendar.refetch()} /> : (
        <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
          <div>
            <h2 className="mb-3 text-base font-semibold text-ink">Хронология выплат</h2>
            {!calendar.data?.days.length ? <EmptyState title="Запланированных дат нет" /> : (
              <ol className="space-y-3">
                {calendar.data.days.map((d) => (
                  <li key={d.date} className="card p-4">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <p className="text-base font-semibold text-ink">{formatDate(d.date)}</p>
                      <Readiness percent={d.readiness_percent} />
                    </div>
                    <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
                      <div><dt className="text-xs text-ink-muted">К выплате</dt><dd>{som(d.to_pay)}</dd></div>
                      <div><dt className="text-xs text-ink-muted">Сотрудников</dt><dd>{d.employees}</dd></div>
                      <div><dt className="text-xs text-ink-muted">Подготовлено</dt><dd>{som(d.prepared)}</dd></div>
                      <div><dt className="text-xs text-ink-muted">Осталось найти</dt><dd className={Number(d.deficit) > 0 ? 'text-danger' : ''}>{som(d.deficit)}</dd></div>
                    </dl>
                    <ul className="mt-2 flex flex-wrap gap-2">
                      {d.plans.map((p) => (
                        <li key={p.id}>
                          <button type="button" className="rounded-lg border border-border px-2 py-1 text-xs hover:bg-surface-hover"
                            onClick={() => navigate(`/accounting/payout-plan/${p.id}`)}>
                            {p.title} · {p.status_display}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ol>
            )}
          </div>
          <div>
            <h2 className="mb-3 text-base font-semibold text-ink">Рекомендуемые даты</h2>
            {!calendar.data?.suggestions.length ? (
              <p className="text-sm text-ink-secondary">Все утверждённые начисления уже включены в планы.</p>
            ) : (
              <ul className="space-y-3">
                {calendar.data.suggestions.map((sug) => (
                  <li key={sug.date ?? 'none'} className="card p-4 text-sm">
                    <p className="font-semibold text-ink">{sug.date ? formatDate(sug.date) : 'Дата не определена'}</p>
                    <p className="text-ink-secondary">{som(sug.amount)} · сотрудников: {sug.employees} · начислений: {sug.payrolls}</p>
                    <p className="text-xs text-ink-muted">{sug.rule}</p>
                    {canEdit ? (
                      <Button size="sm" variant="secondary" className="mt-2" onClick={() => setCreating({ payout_date: sug.date ?? undefined })}>
                        Создать план на дату
                      </Button>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {creating ? (
        <CreatePlanModal initialDate={creating.payout_date} defaultMonth={filters.month} defaultYear={filters.year}
          onClose={() => setCreating(null)} onCreated={(plan) => navigate(`/accounting/payout-plan/${plan.id}`)} />
      ) : null}
    </div>
  )
}

/** Месяц начислений по дате выплаты (правило 15-е / 1-е): 15-го платим за
 * 1–15 того же месяца, 1-го — за вторую половину прошлого месяца. */
function accrualMonthFor(date: string | undefined): { year: number; month: number } {
  const d = date ? new Date(`${date}T00:00:00`) : new Date()
  const month = d.getDate() >= 15 ? d.getMonth() + 1 : d.getMonth()
  return month === 0 ? { year: d.getFullYear() - 1, month: 12 } : { year: d.getFullYear(), month }
}

export function CandidatePicker({ year, month, selected, onChange }: {
  year: number
  month: number
  selected: Record<number, string>
  onChange: (next: Record<number, string>) => void
}) {
  const candidates = usePayoutCandidates({ year, month })
  const rows = candidates.data?.results ?? []
  const toggle = (c: PayoutCandidate) => {
    const next = { ...selected }
    if (c.payroll in next) delete next[c.payroll]
    else next[c.payroll] = c.available
    onChange(next)
  }
  if (candidates.isLoading) return <LoadingState />
  if (candidates.isError) return <ErrorState onRetry={() => candidates.refetch()} />
  if (!rows.length) return <p className="text-sm text-ink-secondary">Утверждённых начислений с остатком за этот месяц нет.</p>
  return (
    <div className="max-h-72 overflow-auto rounded-lg border border-border">
      <table className="data-table">
        <thead>
          <tr><th /><th>Сотрудник</th><th>Период</th><th className="text-right">Остаток</th><th className="text-right">Уже в планах</th><th className="text-right">К выплате</th></tr>
        </thead>
        <tbody>
          {rows.map((c) => {
            const free = Number(c.available) > 0
            const checked = c.payroll in selected
            return (
              <tr key={c.payroll} className={free ? undefined : 'opacity-60'}>
                <td>
                  <input type="checkbox" aria-label={`Включить ${c.employee_name}`} disabled={!free} checked={checked} onChange={() => toggle(c)} />
                </td>
                <td>{c.employee_name}<p className="text-xs text-ink-muted">{c.department_display} · {c.salary_type_display}</p></td>
                <td className="text-sm">{c.period_label}</td>
                <td className="whitespace-nowrap text-right">{som(c.due)}</td>
                <td className="whitespace-nowrap text-right">{Number(c.reserved) > 0 ? som(c.reserved) : '—'}</td>
                <td className="text-right">
                  {checked ? (
                    <Input aria-label={`Сумма для ${c.employee_name}`} type="number" min="0.01" max={c.available} step="0.01" className="w-32"
                      value={selected[c.payroll]} onChange={(e) => onChange({ ...selected, [c.payroll]: e.target.value })} />
                  ) : <span className="text-sm text-ink-secondary">{som(c.available)}</span>}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function CreatePlanModal({ initialDate, defaultMonth, defaultYear, onClose, onCreated }: {
  initialDate?: string
  defaultMonth?: number
  defaultYear?: number
  onClose: () => void
  onCreated: (plan: PayoutPlanDetail) => void
}) {
  const guess = useMemo(() => accrualMonthFor(initialDate), [initialDate])
  const [form, setForm] = useState({
    title: '', payout_date: initialDate ?? '', year: defaultYear && defaultMonth ? defaultYear : guess.year,
    month: defaultMonth ?? guess.month, prepared_amount: '0', comment: '',
  })
  const [selected, setSelected] = useState<Record<number, string>>({})
  const { run, busy } = useRunner()
  const mutate = useAccountingMutation((fn: () => Promise<PayoutPlanDetail>) => fn())
  const total = Object.values(selected).reduce((sum, v) => sum + (Number(v) || 0), 0)
  const valid = form.title.trim() && form.payout_date && Number(form.prepared_amount) >= 0
    && Object.values(selected).every((v) => Number(v) > 0)

  const submit = () => run(async () => {
    const plan = await mutate.mutateAsync(() => accountingApi.createPayoutPlan({
      title: form.title.trim(), year: form.year, month: form.month, payout_date: form.payout_date,
      prepared_amount: form.prepared_amount || '0', comment: form.comment,
      lines: Object.entries(selected).map(([payroll, amount]) => ({ payroll: Number(payroll), amount })),
    }))
    onCreated(plan)
  }, 'План создан (черновик)')

  return (
    <Modal isOpen onClose={onClose} size="lg" title="Новый план выплат">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Название" required htmlFor="np-title">
          <Input id="np-title" value={form.title} placeholder="Например: зарплата за сентябрь"
            onChange={(e) => setForm({ ...form, title: e.target.value })} />
        </Field>
        <Field label="Дата выплаты" required htmlFor="np-date">
          <Input id="np-date" type="date" value={form.payout_date} onChange={(e) => setForm({ ...form, payout_date: e.target.value })} />
        </Field>
        <Field label="Месяц начислений" htmlFor="np-month">
          <div className="flex gap-2">
            <Select id="np-month" value={String(form.month)} options={MONTHS.map((label, i) => ({ value: String(i + 1), label }))}
              onChange={(e) => { setForm({ ...form, month: Number(e.target.value) }); setSelected({}) }} />
            <Select aria-label="Год начислений" className="w-28" value={String(form.year)} options={YEARS}
              onChange={(e) => { setForm({ ...form, year: Number(e.target.value) }); setSelected({}) }} />
          </div>
        </Field>
        <Field label="Подготовлено средств, сом" htmlFor="np-prepared" help="Вносится вручную; это не выплата">
          <Input id="np-prepared" type="number" min="0" step="0.01" value={form.prepared_amount}
            onChange={(e) => setForm({ ...form, prepared_amount: e.target.value })} />
        </Field>
      </div>
      <Field label="Комментарий" htmlFor="np-comment" className="mt-3">
        <Textarea id="np-comment" rows={2} value={form.comment} onChange={(e) => setForm({ ...form, comment: e.target.value })} />
      </Field>
      <div className="mt-4">
        <p className="mb-2 text-sm font-medium text-ink">Начисления к выплате</p>
        <CandidatePicker year={form.year} month={form.month} selected={selected} onChange={setSelected} />
        <p className="mt-2 text-sm text-ink-secondary">
          Выбрано: {Object.keys(selected).length} · сумма {som(total.toFixed(2))}
          {Number(form.prepared_amount) < total ? ` · дефицит ${som((total - Number(form.prepared_amount)).toFixed(2))}` : ''}
        </p>
      </div>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Отмена</Button>
        <Button isLoading={busy} disabled={!valid} onClick={submit}>Создать черновик</Button>
      </div>
    </Modal>
  )
}
