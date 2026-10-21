import { useState } from 'react'
import type { ReactNode } from 'react'
import { AlertTriangle, CalendarClock, Plus, Users, Wallet } from 'lucide-react'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'

import { billingApi } from '@/api/billing'
import { newIdempotencyKey } from '@/api/accounting'
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
import type { BillingFilters, BillingOptions, DebtorRow, InvoiceRow, InvoiceStatus } from '@/types/billing'

import { BillingStudents } from './BillingStudents'
import { ReasonModal, Section, formatDate, formatDateTime, som, today, useRunner } from './shared'

type Tab = 'students' | 'overview' | 'debts' | 'invoices' | 'payments' | 'contacts' | 'approvals'

const TABS: { key: Tab; label: string }[] = [
  { key: 'students', label: 'Студенты' },
  { key: 'overview', label: 'Обзор' },
  { key: 'debts', label: 'Должники' },
  { key: 'invoices', label: 'Начисления' },
  { key: 'payments', label: 'Поступления' },
  { key: 'contacts', label: 'Контакты с родителями' },
  { key: 'approvals', label: 'Скидки на согласование' },
]

const STATUS_TONE: Record<InvoiceStatus, BadgeTone> = {
  DRAFT: 'muted', OPEN: 'info', PARTIALLY_PAID: 'warning', PAID: 'success', OVERDUE: 'danger', VOID: 'muted',
}

export function InvoiceStatusBadge({ status, label }: { status: InvoiceStatus; label: string }) {
  return <Badge tone={STATUS_TONE[status]}>{label}</Badge>
}

const KEY = ['billing'] as const

function useBillingOptions() {
  return useQuery({ queryKey: [...KEY, 'options'], queryFn: billingApi.options, staleTime: 5 * 60 * 1000 })
}

function useBillingMe() {
  return useQuery({ queryKey: [...KEY, 'me'], queryFn: billingApi.me, staleTime: 5 * 60 * 1000 })
}

/** Отдельный раздел «Оплата обучения»: деньги по пакетам уроков, долги и работа с родителями. */
export function BillingPage() {
  const [tab, setTab] = useState<Tab>('students')
  const [filters, setFilters] = useState<BillingFilters>({})
  const [paying, setPaying] = useState<{ profile: number; student: string } | null>(null)
  const [contacting, setContacting] = useState<{ profile: number; student: string; invoice?: number } | null>(null)
  const options = useBillingOptions()
  const me = useBillingMe()
  const canOperate = me.data?.can_record_payments ?? false

  return (
    <div>
      <PageHeader
        title="Оплата обучения"
        description="Пакеты уроков, начисления, долги и поступления. Начисления создаются автоматически по проведённым урокам; деньги не удаляются — ошибки исправляются сторно."
      />
      <BillingFilterBar filters={filters} onChange={setFilters} options={options.data} />
      <Tabs aria-label="Разделы оплаты" items={TABS} value={tab} onChange={setTab} />
      <div className="mt-4">
        {tab === 'students' ? (
          <BillingStudents filters={filters} options={options.data} caps={me.data}
            onPay={canOperate ? setPaying : undefined} onContact={canOperate ? setContacting : undefined} />
        ) : null}
        {tab === 'overview' ? (
          <Overview filters={filters} onPay={canOperate ? setPaying : undefined} onContact={canOperate ? setContacting : undefined} />
        ) : null}
        {tab === 'debts' ? <Debts filters={filters} onPay={canOperate ? setPaying : undefined} onContact={canOperate ? setContacting : undefined} /> : null}
        {tab === 'invoices' ? <Invoices filters={filters} /> : null}
        {tab === 'payments' ? <Payments filters={filters} canOperate={canOperate} /> : null}
        {tab === 'contacts' ? <Contacts filters={filters} /> : null}
        {tab === 'approvals' ? <Approvals canDecide={me.data?.is_billing_admin ?? false} /> : null}
      </div>
      {paying ? <PaymentModal target={paying} onClose={() => setPaying(null)} /> : null}
      {contacting ? <ContactModal target={contacting} options={options.data} onClose={() => setContacting(null)} /> : null}
    </div>
  )
}

function BillingFilterBar({ filters, onChange, options }: {
  filters: BillingFilters
  onChange: (f: BillingFilters) => void
  options?: BillingOptions
}) {
  const num = (v: string) => Number(v) || undefined
  return (
    <FilterBar>
      <FilterField>
        <Select aria-label="Группа" value={filters.group ? String(filters.group) : ''} placeholder="Все группы"
          options={(options?.groups ?? []).map((g) => ({ value: String(g.id), label: g.name }))}
          onChange={(e) => onChange({ ...filters, group: num(e.target.value) })} />
      </FilterField>
      <FilterField>
        <Select aria-label="Направление" value={filters.subject ? String(filters.subject) : ''} placeholder="Все направления"
          options={(options?.subjects ?? []).map((s) => ({ value: String(s.id), label: s.name }))}
          onChange={(e) => onChange({ ...filters, subject: num(e.target.value) })} />
      </FilterField>
      <FilterField>
        <Select aria-label="Статус начисления" value={filters.status ?? ''} placeholder="Все статусы"
          options={(options?.invoice_statuses ?? []).map((s) => ({ value: s.value, label: s.label }))}
          onChange={(e) => onChange({ ...filters, status: (e.target.value || undefined) as InvoiceStatus | undefined })} />
      </FilterField>
      <FilterField>
        <Select aria-label="Ответственный бухгалтер" value={filters.accountant ? String(filters.accountant) : ''}
          placeholder="Все бухгалтеры"
          options={(options?.accountants ?? []).map((a) => ({ value: String(a.id), label: a.name }))}
          onChange={(e) => onChange({ ...filters, accountant: num(e.target.value) })} />
      </FilterField>
      <FilterField label="С" htmlFor="bill-from">
        <Input id="bill-from" type="date" value={filters.date_from ?? ''}
          onChange={(e) => onChange({ ...filters, date_from: e.target.value || undefined })} />
      </FilterField>
      <FilterField label="По" htmlFor="bill-to">
        <Input id="bill-to" type="date" value={filters.date_to ?? ''}
          onChange={(e) => onChange({ ...filters, date_to: e.target.value || undefined })} />
      </FilterField>
    </FilterBar>
  )
}

function Loadable<T>({ query, empty, children }: {
  query: { isLoading: boolean; isError: boolean; refetch: () => unknown; data?: T }
  empty?: (data: T) => boolean
  children: (data: T) => ReactNode
}) {
  if (query.isLoading) return <LoadingState />
  if (query.isError || query.data === undefined) return <ErrorState onRetry={() => query.refetch()} />
  if (empty?.(query.data)) return <EmptyState title="Нет данных" />
  return <>{children(query.data)}</>
}

type RowAction = (target: { profile: number; student: string; invoice?: number }) => void

function Overview({ filters, onPay, onContact }: { filters: BillingFilters; onPay?: RowAction; onContact?: RowAction }) {
  const dashboard = useQuery({
    queryKey: [...KEY, 'dashboard', filters], queryFn: () => billingApi.dashboard(filters), placeholderData: keepPreviousData,
  })
  return (
    <Loadable query={dashboard}>
      {(d) => (
        <>
          <StatGrid>
            <StatCard label="Студентов ожидают оплаты" value={d.students_awaiting} icon={Users}
              hint={`${d.invoices_awaiting} начисл. · активных студентов ${d.active_students}`} />
            <StatCard label="Общая задолженность" value={som(d.total_debt)} icon={Wallet}
              tone={Number(d.total_debt) > 0 ? 'warning' : 'default'} />
            <StatCard label="Просрочено начислений" value={d.overdue_invoices} icon={AlertTriangle}
              tone={d.overdue_invoices > 0 ? 'danger' : 'default'}
              hint={`${d.overdue_students} студ. · ${som(d.overdue_amount)}`} />
            <StatCard label="Поступления за период" value={som(d.received.net)} icon={CalendarClock}
              hint={`${formatDate(d.date_from)} – ${formatDate(d.date_to)}: ${d.received.count} плат., возвраты ${som(d.received.refunds)}`} />
          </StatGrid>
          <StatGrid className="mt-3">
            <StatCard label="Доступные авансы" value={som(d.credit_total)} hint={`${d.credit_profiles} студ.`} />
            <StatCard label="Пакеты заканчиваются" value={d.packages_ending} />
            <StatCard label="Открытые задачи" value={d.open_tasks} hint={`Пора связаться: ${d.follow_ups_due}`} />
          </StatGrid>
          <Section title={`Скоро срок оплаты (${d.due_soon_days} дн.)`}>
            <InvoiceTable rows={d.due_soon} onPay={onPay} onContact={onContact} />
          </Section>
          <Section title="Частичная оплата">
            <InvoiceTable rows={d.partial} onPay={onPay} onContact={onContact} />
          </Section>
          <Section title="Последние контакты с родителями">
            {d.contacts.length === 0 ? <EmptyState title="Контактов нет" /> : (
              <div className="card overflow-x-auto">
                <table className="data-table">
                  <thead><tr><th>Когда</th><th>Студент</th><th>Канал</th><th>Результат</th><th>Обещано</th><th>Сотрудник</th><th>Комментарий</th></tr></thead>
                  <tbody>
                    {d.contacts.map((c) => (
                      <tr key={c.id}>
                        <td>{formatDateTime(c.contacted_at)}</td><td>{c.student_name}</td><td>{c.channel_display}</td>
                        <td>{c.result_display}</td><td>{formatDate(c.promised_payment_date)}</td><td>{c.staff}</td>
                        <td className="max-w-xs truncate">{c.comment}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>
        </>
      )}
    </Loadable>
  )
}

function InvoiceTable({ rows, onPay, onContact }: { rows: InvoiceRow[]; onPay?: RowAction; onContact?: RowAction }) {
  if (rows.length === 0) return <EmptyState title="Нет начислений" />
  return (
    <div className="card overflow-x-auto">
      <table className="data-table">
        <thead>
          <tr><th>Начисление</th><th>Студент</th><th>Группа</th><th>Направление</th><th>Пакет</th>
            <th className="text-right">Сумма</th><th className="text-right">Оплачено</th><th className="text-right">Остаток</th>
            <th>Срок</th><th>Статус</th><th /></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.invoice}>
              <td>{r.number}</td><td>{r.student_name}</td><td>{r.group ?? '—'}</td><td>{r.subject ?? '—'}</td>
              <td>№{r.package_number}</td><td className="text-right">{som(r.amount)}</td>
              <td className="text-right">{som(r.paid)}</td><td className="text-right font-medium">{som(r.balance)}</td>
              <td>{formatDate(r.due_date)}</td><td><InvoiceStatusBadge status={r.status} label={r.status_display} /></td>
              <td className="whitespace-nowrap text-right">
                {onPay ? <Button size="sm" variant="ghost" onClick={() => onPay({ profile: r.profile, student: r.student_name })}>Платёж</Button> : null}
                {onContact ? <Button size="sm" variant="ghost" onClick={() => onContact({ profile: r.profile, student: r.student_name, invoice: r.invoice })}>Контакт</Button> : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Debts({ filters, onPay, onContact }: { filters: BillingFilters; onPay?: RowAction; onContact?: RowAction }) {
  const debts = useQuery({ queryKey: [...KEY, 'debts', filters], queryFn: () => billingApi.debts(filters), placeholderData: keepPreviousData })
  return (
    <Loadable query={debts} empty={(d) => d.count === 0}>
      {(d) => (
        <div className="card overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr><th>Студент</th><th>Группа</th><th>Родитель</th><th className="text-right">Счетов</th>
                <th className="text-right">Долг</th><th className="text-right">Просрочено</th><th>Дней</th>
                <th>Обещано</th><th>Следующий контакт</th><th>Последний контакт</th><th /></tr>
            </thead>
            <tbody>
              {d.results.map((r: DebtorRow) => (
                <tr key={r.profile}>
                  <td>{r.student_name}{r.has_partial ? <Badge tone="warning" className="ml-2">частично</Badge> : null}</td>
                  <td>{r.group ?? '—'}</td>
                  <td>{r.parent_name || '—'}<div className="text-xs text-ink-muted">{r.parent_phone}</div></td>
                  <td className="text-right">{r.invoices}</td>
                  <td className="text-right font-medium">{som(r.debt)}</td>
                  <td className="text-right">{som(r.overdue_amount)}</td>
                  <td>{r.max_days_overdue || '—'}</td>
                  <td>{formatDate(r.promised_date)}</td>
                  <td>{formatDate(r.next_contact_date)}</td>
                  <td>{r.last_contact_result ?? '—'}<div className="text-xs text-ink-muted">{formatDateTime(r.last_contact_at)}</div></td>
                  <td className="whitespace-nowrap text-right">
                    {onPay ? <Button size="sm" variant="ghost" onClick={() => onPay({ profile: r.profile, student: r.student_name })}>Платёж</Button> : null}
                    {onContact ? <Button size="sm" variant="ghost" onClick={() => onContact({ profile: r.profile, student: r.student_name })}>Контакт</Button> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Loadable>
  )
}

function Invoices({ filters }: { filters: BillingFilters }) {
  const [page, setPage] = useState(1)
  const invoices = useQuery({
    queryKey: [...KEY, 'invoices', filters, page], queryFn: () => billingApi.invoices({ ...filters, page }),
    placeholderData: keepPreviousData,
  })
  return (
    <Loadable query={invoices} empty={(d) => d.count === 0}>
      {(d) => (
        <>
          <div className="card overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr><th>Номер</th><th>Студент</th><th>Направление</th><th>Пакет</th><th className="text-right">Сумма</th>
                  <th className="text-right">Оплачено</th><th className="text-right">Корр.</th><th className="text-right">Остаток</th>
                  <th>Начислено</th><th>Срок</th><th>Статус</th></tr>
              </thead>
              <tbody>
                {d.results.map((i) => (
                  <tr key={i.id}>
                    <td>{i.number}</td><td>{i.student_name}</td><td>{i.subject_name ?? '—'}</td><td>№{i.package_number}</td>
                    <td className="text-right">{som(i.amount)}</td><td className="text-right">{som(i.amount_paid)}</td>
                    <td className="text-right">{som(i.amount_adjusted)}</td><td className="text-right font-medium">{som(i.balance)}</td>
                    <td>{formatDate(i.issue_date)}</td><td>{formatDate(i.due_date)}</td>
                    <td><InvoiceStatusBadge status={i.status} label={i.status_display} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={page} pageSize={50} totalCount={d.count} onPageChange={setPage} />
        </>
      )}
    </Loadable>
  )
}

function Payments({ filters, canOperate }: { filters: BillingFilters; canOperate: boolean }) {
  const [page, setPage] = useState(1)
  const [reversing, setReversing] = useState<number | null>(null)
  const client = useQueryClient()
  const { run } = useRunner()
  const payments = useQuery({
    queryKey: [...KEY, 'payments', filters, page], queryFn: () => billingApi.payments({ ...filters, page }),
    placeholderData: keepPreviousData,
  })
  return (
    <>
      <Loadable query={payments} empty={(d) => d.count === 0}>
        {(d) => (
          <>
            <div className="card overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr><th>Дата</th><th>Студент</th><th>Назначение</th><th className="text-right">Сумма</th>
                    <th className="text-right">Аванс</th><th>Распределено</th><th>Документ</th><th>Статус</th><th /></tr>
                </thead>
                <tbody>
                  {d.results.map((p) => (
                    <tr key={p.id} className={p.status === 'void' ? 'opacity-60' : undefined}>
                      <td>{formatDate(p.received_date)}</td><td>{p.student_name}</td>
                      <td>{p.kind === 'refund' ? 'Возврат' : p.purpose === 'reservation' ? 'Бронь' : 'Обучение'}</td>
                      <td className="text-right">{p.kind === 'refund' ? '−' : ''}{som(p.amount)}</td>
                      <td className="text-right">{p.unallocated ? som(p.unallocated) : '—'}</td>
                      <td className="text-xs">{p.allocations.filter((a) => a.status === 'ACTIVE').map((a) => `${a.invoice_number}: ${som(a.amount)}`).join('; ') || '—'}</td>
                      <td>{p.reference || '—'}</td>
                      <td>{p.status === 'void' ? <Badge>Отменён</Badge> : <Badge tone="success">Проведён</Badge>}</td>
                      <td className="text-right">
                        {canOperate && p.status === 'confirmed'
                          ? <Button size="sm" variant="ghost" onClick={() => setReversing(p.id)}>Сторно</Button> : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={page} pageSize={50} totalCount={d.count} onPageChange={setPage} />
          </>
        )}
      </Loadable>
      <ReasonModal
        isOpen={reversing !== null}
        title="Сторно платежа"
        description="Распределения платежа будут сторнированы, начисления снова будут ждать оплаты. Сам платёж останется в истории."
        confirmLabel="Сторнировать"
        tone="danger"
        onClose={() => setReversing(null)}
        onConfirm={(reason) => run(async () => {
          await billingApi.reversePayment(reversing as number, reason)
          await client.invalidateQueries({ queryKey: KEY })
        }, 'Платёж сторнирован')}
      />
    </>
  )
}

function Contacts({ filters }: { filters: BillingFilters }) {
  const [page, setPage] = useState(1)
  const contacts = useQuery({
    queryKey: [...KEY, 'contacts', filters, page], queryFn: () => billingApi.contacts({ ...filters, page }),
    placeholderData: keepPreviousData,
  })
  return (
    <Loadable query={contacts} empty={(d) => d.count === 0}>
      {(d) => (
        <>
          <div className="card overflow-x-auto">
            <table className="data-table">
              <thead><tr><th>Когда</th><th>Студент</th><th>Начисление</th><th>Канал</th><th>Результат</th><th>Обещано</th><th>Следующий</th><th>Сотрудник</th><th>Комментарий</th></tr></thead>
              <tbody>
                {d.results.map((c) => (
                  <tr key={c.id}>
                    <td>{formatDateTime(c.contacted_at)}</td><td>{c.student_name}</td><td>{c.invoice ?? '—'}</td>
                    <td>{c.channel_display}</td><td>{c.result_display}</td><td>{formatDate(c.promised_payment_date)}</td>
                    <td>{formatDate(c.next_contact_date)}</td><td>{c.staff}</td><td className="max-w-xs truncate">{c.comment}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={page} pageSize={50} totalCount={d.count} onPageChange={setPage} />
        </>
      )}
    </Loadable>
  )
}

function Approvals({ canDecide }: { canDecide: boolean }) {
  const client = useQueryClient()
  const { run } = useRunner()
  const changes = useQuery({ queryKey: [...KEY, 'terms'], queryFn: () => billingApi.termsChanges('PENDING') })
  return (
    <Loadable query={changes} empty={(d) => d.count === 0}>
      {(d) => (
        <div className="card overflow-x-auto">
          <table className="data-table">
            <thead><tr><th>Студент</th><th>Условия</th><th>Основание</th><th>Назначил</th><th>Когда</th><th /></tr></thead>
            <tbody>
              {d.results.map((c) => (
                <tr key={c.id}>
                  <td>{c.student_name}</td>
                  <td>{c.custom_price ? `Цена ${som(c.custom_price)}` : ''} {c.discount_type === 'PERCENT' ? `Скидка ${c.discount_value}%` : c.discount_type === 'FIXED' ? `Скидка ${som(c.discount_value)}` : ''}</td>
                  <td className="max-w-xs truncate">{c.reason}</td><td>{c.requested_by_name ?? '—'}</td><td>{formatDateTime(c.requested_at)}</td>
                  <td className="whitespace-nowrap text-right">
                    {canDecide ? (
                      <>
                        <Button size="sm" onClick={() => run(async () => {
                          await billingApi.decideTerms(c.id, true)
                          await client.invalidateQueries({ queryKey: KEY })
                        }, 'Скидка согласована')}>Согласовать</Button>
                        <Button size="sm" variant="ghost" onClick={() => run(async () => {
                          await billingApi.decideTerms(c.id, false)
                          await client.invalidateQueries({ queryKey: KEY })
                        }, 'Скидка отклонена')}>Отклонить</Button>
                      </>
                    ) : <span className="text-xs text-ink-muted">Решает администратор</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Loadable>
  )
}

const METHODS = [
  { value: 'cash', label: 'Наличные' }, { value: 'bank', label: 'Банковский перевод' },
  { value: 'card', label: 'Карта / QR' }, { value: 'other', label: 'Другое' },
]

function PaymentModal({ target, onClose }: { target: { profile: number; student: string }; onClose: () => void }) {
  const client = useQueryClient()
  const { run, busy } = useRunner()
  // Один ключ на открытую форму: двойной клик или повтор после обрыва сети не создаст второй платёж.
  const [key] = useState(newIdempotencyKey)
  const [form, setForm] = useState({ amount: '', received_date: today(), method: 'cash', reference: '', comment: '', prepay_packages: '0' })
  return (
    <Modal isOpen onClose={onClose} title={`Платёж: ${target.student}`}>
      <div className="space-y-3">
        <Field label="Сумма, сом" htmlFor="pay-amount" required>
          <Input id="pay-amount" inputMode="decimal" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
        </Field>
        <Field label="Дата поступления" htmlFor="pay-date" required>
          <Input id="pay-date" type="date" max={today()} value={form.received_date} onChange={(e) => setForm({ ...form, received_date: e.target.value })} />
        </Field>
        <Field label="Способ" htmlFor="pay-method">
          <Select id="pay-method" options={METHODS} value={form.method} onChange={(e) => setForm({ ...form, method: e.target.value })} />
        </Field>
        <Field label="Оплата вперёд, пакетов" htmlFor="pay-prepay" help="Создаст начисления за следующие пакеты и распределит по ним деньги; остаток — аванс.">
          <Input id="pay-prepay" type="number" min={0} max={12} value={form.prepay_packages} onChange={(e) => setForm({ ...form, prepay_packages: e.target.value })} />
        </Field>
        <Field label="Номер документа" htmlFor="pay-ref">
          <Input id="pay-ref" value={form.reference} onChange={(e) => setForm({ ...form, reference: e.target.value })} />
        </Field>
        <Field label="Комментарий" htmlFor="pay-comment">
          <Textarea id="pay-comment" rows={2} value={form.comment} onChange={(e) => setForm({ ...form, comment: e.target.value })} />
        </Field>
      </div>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Отмена</Button>
        <Button leftIcon={<Plus className="size-4" />} isLoading={busy} disabled={!form.amount}
          onClick={async () => {
            const ok = await run(async () => {
              await billingApi.recordPayment({
                profile: target.profile, amount: form.amount, received_date: form.received_date, method: form.method,
                reference: form.reference, comment: form.comment, prepay_packages: Number(form.prepay_packages) || 0,
              }, key)
              await client.invalidateQueries({ queryKey: KEY })
            }, 'Платёж зарегистрирован')
            if (ok) onClose()
          }}>Зарегистрировать</Button>
      </div>
    </Modal>
  )
}

function ContactModal({ target, options, onClose }: {
  target: { profile: number; student: string; invoice?: number }
  options?: BillingOptions
  onClose: () => void
}) {
  const client = useQueryClient()
  const { run, busy } = useRunner()
  const [form, setForm] = useState({ channel: 'CALL', result: 'ANSWERED', comment: '', promised_payment_date: '', next_contact_date: '' })
  return (
    <Modal isOpen onClose={onClose} title={`Контакт с родителем: ${target.student}`}>
      <div className="space-y-3">
        <Field label="Канал" htmlFor="c-channel">
          <Select id="c-channel" options={options?.contact_channels ?? []} value={form.channel} onChange={(e) => setForm({ ...form, channel: e.target.value })} />
        </Field>
        <Field label="Результат" htmlFor="c-result">
          <Select id="c-result" options={options?.contact_results ?? []} value={form.result} onChange={(e) => setForm({ ...form, result: e.target.value })} />
        </Field>
        <Field label="Обещанная дата оплаты" htmlFor="c-promise" required={form.result === 'PROMISED'}>
          <Input id="c-promise" type="date" value={form.promised_payment_date} onChange={(e) => setForm({ ...form, promised_payment_date: e.target.value })} />
        </Field>
        <Field label="Следующий контакт" htmlFor="c-next" required={form.result === 'FOLLOW_UP'}>
          <Input id="c-next" type="date" value={form.next_contact_date} onChange={(e) => setForm({ ...form, next_contact_date: e.target.value })} />
        </Field>
        <Field label="Комментарий" htmlFor="c-comment">
          <Textarea id="c-comment" rows={3} value={form.comment} onChange={(e) => setForm({ ...form, comment: e.target.value })} />
        </Field>
      </div>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Отмена</Button>
        <Button isLoading={busy} onClick={async () => {
          const ok = await run(async () => {
            await billingApi.addContact({
              profile: target.profile, invoice: target.invoice ?? null, channel: form.channel, result: form.result,
              comment: form.comment, promised_payment_date: form.promised_payment_date || null,
              next_contact_date: form.next_contact_date || null,
            })
            await client.invalidateQueries({ queryKey: KEY })
          }, 'Контакт записан')
          if (ok) onClose()
        }}>Записать</Button>
      </div>
    </Modal>
  )
}
