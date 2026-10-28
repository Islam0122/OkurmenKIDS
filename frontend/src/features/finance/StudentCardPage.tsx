import { useState } from 'react'
import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ChevronDown, Pencil, Phone, Plus } from 'lucide-react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'

import { financeApi } from '@/api/finance'
import { newIdempotencyKey } from '@/api/accounting'
import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import { BackLink } from '@/components/ui/BackLink'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { DataTable } from '@/components/ui/DataTable'
import { Drawer } from '@/components/ui/Drawer'
import { EmptyState } from '@/components/ui/EmptyState'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { ReasonModal } from '@/features/accounting/shared'
import { Field } from '@/features/worklog/formUi'
import type { ContractCard, Invoice, InvoiceStatus, Payment, Reservation, StudyProgress } from '@/types/finance'
import { cn } from '@/utils/cn'

import { OperationsTable, ReservationBlock, ScheduleBlock, operationType } from './CardSections'

import {
  Amount,
  ContactModal,
  ContractStatusBadge,
  FINANCE_KEY,
  InvoiceStatusBadge,
  Loadable,
  StageBadge,
  formatDate,
  formatDateTime,
  som,
  today,
  useFinanceMe,
  useFinanceOptions,
  useInvalidateFinance,
  useRunner,
} from './ui'

const PACKAGE_STATUS: Record<string, { label: string; tone: BadgeTone }> = {
  PLANNED: { label: 'Будущий', tone: 'muted' }, ACTIVE: { label: 'Текущий', tone: 'info' },
  COMPLETED: { label: 'Пройден', tone: 'success' }, CANCELLED: { label: 'Отменён', tone: 'muted' },
}

type InvoiceFilter = 'all' | 'overdue' | 'unpaid' | 'partial' | 'paid'
const INVOICE_FILTERS: { value: InvoiceFilter; label: string }[] = [
  { value: 'all', label: 'Все' }, { value: 'overdue', label: 'Просроченные' }, { value: 'unpaid', label: 'Неоплаченные' },
  { value: 'partial', label: 'Частично оплаченные' }, { value: 'paid', label: 'Оплаченные' },
]
const UNPAID: InvoiceStatus[] = ['OPEN', 'PARTIALLY_PAID', 'OVERDUE']

function matches(i: Invoice, filter: InvoiceFilter): boolean {
  const unpaid = UNPAID.includes(i.status)
  switch (filter) {
    case 'overdue': return unpaid && (i.status === 'OVERDUE' || i.stage === 'overdue')
    case 'unpaid': return unpaid
    case 'partial': return unpaid && Number(i.amount_paid) + Number(i.amount_adjusted) > 0
    case 'paid': return i.status === 'PAID'
    default: return true
  }
}

const nonZero = (v: string | null | undefined) => v !== null && v !== undefined && Number(v) !== 0

/** Раскрывающийся раздел: заголовок всегда виден, второстепенное содержимое — по нажатию. */
function Collapsible({ title, defaultOpen = true, actions, children, id }: {
  title: string; defaultOpen?: boolean; actions?: ReactNode; children: ReactNode; id?: string
}) {
  const [open, setOpen] = useState(defaultOpen)
  const bodyId = `section-${id ?? title}`
  return (
    <section className="mt-6" id={id}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold text-ink">
          <button type="button" aria-expanded={open} aria-controls={bodyId} onClick={() => setOpen(!open)}
            className="inline-flex items-center gap-1.5 rounded-md text-left hover:text-brand-700 focus-visible:outline-2 focus-visible:outline-brand-500">
            <ChevronDown className={cn('size-4 transition-transform', !open && '-rotate-90')} aria-hidden />{title}
          </button>
        </h2>
        {open ? actions : null}
      </div>
      {open ? <div id={bodyId}>{children}</div> : null}
    </section>
  )
}

function Kpi({ label, value, tone, children }: { label: string; value: string; tone?: 'danger' | 'brand' | 'success'; children?: ReactNode }) {
  return (
    <div className="card flex min-w-0 flex-col p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-secondary">{label}</p>
      <p className={cn('mt-1 text-xl font-semibold tabular-nums text-ink sm:text-2xl', tone === 'danger' && 'text-danger',
        tone === 'brand' && 'text-brand-700', tone === 'success' && 'text-brand-700')}>{value}</p>
      {children ? <div className="mt-2 space-y-0.5 text-xs text-ink-secondary">{children}</div> : null}
    </div>
  )
}

function Line({ label, value, tone }: { label: string; value: ReactNode; tone?: 'danger' | 'muted' }) {
  return (
    <p className={cn('flex justify-between gap-2', tone === 'danger' && 'text-danger', tone === 'muted' && 'text-ink-muted')}>
      <span>{label}</span><span className="whitespace-nowrap tabular-nums">{value}</span>
    </p>
  )
}

/** Три независимых показателя (backend `progress`): учебный месяц группы, посещаемость ученика,
 * финансовый пакет договора. Месяц группы не подтверждает посещение и не меняет начисления. */
function ProgressBlock({ progress, subject }: { progress: StudyProgress; subject: string }) {
  const g = progress.group
  const pkg = progress.package
  return (
    <div className="grid gap-3 sm:grid-cols-3" data-testid="study-progress">
      <div className="rounded-xl border border-border bg-surface p-3 text-sm">
        <p className="text-xs text-ink-secondary">Учебный месяц группы{g.group_name ? ` · ${g.group_name}` : ''}</p>
        {g.month ? (
          <p><b>Месяц группы {g.month} из {g.months}</b> · {subject} {g.in_month}/{g.per_month}
            <span className="block text-xs text-ink-secondary">проведено занятий группы: {g.held} из {g.total}</span></p>
        ) : <p className="text-warning">{g.warning}</p>}
      </div>
      <div className="rounded-xl border border-border bg-surface p-3 text-sm">
        <p className="text-xs text-ink-secondary">Посещаемость ученика</p>
        <p>{progress.attendance.attended === null ? '—' : <>посетил <b>{progress.attendance.attended}</b> из {progress.attendance.held} занятий {subject} группы</>}</p>
      </div>
      <div className="rounded-xl border border-border bg-surface p-3 text-sm">
        <p className="text-xs text-ink-secondary">Финансовый пакет договора</p>
        <p>{pkg ? <><b>№{pkg.number}: {pkg.lessons_used}/{pkg.lessons_total}</b>
          <span className="block text-xs text-ink-secondary">засчитано по договору: {pkg.counted}
            {pkg.contract_months && pkg.contract_per_month ? ` из ${pkg.contract_months * pkg.contract_per_month}` : ''} · начисления и сроки — по пакету</span></> : '—'}</p>
      </div>
    </div>
  )
}

export function StudentCardPage() {
  const { profileId } = useParams()
  const id = Number(profileId)
  const location = useLocation()
  const query = useQuery({ queryKey: [...FINANCE_KEY, 'card', id], queryFn: () => financeApi.card(id) })
  const from = (location.state as { from?: string } | null)?.from ?? '/finance/students'
  return (
    <div>
      <BackLink to={from}>Назад к списку</BackLink>
      <Loadable query={query}>{(card) => <Card360 card={card} />}</Loadable>
    </div>
  )
}

function Card360({ card }: { card: ContractCard }) {
  const navigate = useNavigate()
  const me = useFinanceMe()
  const { contract: c, summary, row } = card
  const [contact, setContact] = useState(false)
  const [terms, setTerms] = useState(false)
  const [creditHistory, setCreditHistory] = useState(false)
  const [reversing, setReversing] = useState<Payment | null>(null)
  const [reservationPay, setReservationPay] = useState<Reservation | null>(null)
  const [invoiceFilter, setInvoiceFilter] = useState<InvoiceFilter>('all')
  const [openInvoice, setOpenInvoice] = useState<Invoice | null>(null)
  const invalidate = useInvalidateFinance()
  const { run } = useRunner()
  const canPay = me.data?.can_record_payments ?? false
  const canTerms = (me.data?.can_register ?? false) && c.is_course && (c.status === 'ACTIVE' || c.status === 'PAUSED')
  const debt = card.debt
  const invoices = card.invoices.filter((i) => matches(i, invoiceFilter))
  const moneyGap = card.payments ? Number(summary.net_received) - Number(summary.allocated) - Number(summary.credit) : 0
  const futureDue = summary.future ?? '0.00'
  const nextDue = debt?.next_due
  const overdue = nonZero(summary.overdue)

  return (
    <div>
      <header className="card mb-4 p-4 sm:p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="min-w-0 text-xl font-semibold text-ink sm:text-2xl">{c.student_name}</h1>
              <ContractStatusBadge status={c.status} label={c.status_display} />
              <StageBadge stage={row.stage} />
            </div>
            <p className="mt-1 text-sm text-ink-secondary">
              {c.group_name ?? 'Без группы'} · {c.program_name ?? c.plan_name}{c.subject_name ? ` · ${c.subject_name}` : ''}
            </p>
            <p className="mt-0.5 text-sm text-ink-secondary">
              {c.parent_name || 'родитель не указан'}
              {c.parent_phone ? <> · <a href={`tel:${c.parent_phone.replace(/[^+\d]/g, '')}`} className="text-brand-700 hover:underline">{c.parent_phone}</a></> : null}
            </p>
            <p className="mt-2 text-sm" data-testid="finance-status">
              {summary.course_paid_in_full ? <span className="text-brand-700">Курс оплачен полностью</span>
                : nonZero(summary.due_now) ? <span className={cn(overdue && 'text-danger')}>
                  Долг {som(summary.due_now)}{overdue ? `, из них просрочено ${som(summary.overdue)}` : ''}</span>
                  : <span className="text-ink-secondary">Текущего долга нет</span>}
              {summary.final_course_price ? <span className="text-ink-secondary"> · осталось оплатить {som(summary.net_to_pay)}</span> : null}
            </p>
          </div>
          <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:justify-end">
            {canPay ? <Button className="col-span-2 sm:col-span-1" leftIcon={<Plus className="size-4" />}
              onClick={() => navigate(`/finance/payments/new?profile=${c.id}`)}>Добавить платёж</Button> : null}
            {canPay ? <Button variant="secondary" leftIcon={<Phone className="size-4" />} onClick={() => setContact(true)}>Контакт</Button> : null}
            {canTerms ? <Button variant="secondary" leftIcon={<Pencil className="size-4" />} onClick={() => setTerms(true)}>Стоимость курса</Button> : null}
          </div>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 xl:grid-cols-4">
        <Kpi label="Долг на сегодня" value={som(summary.due_now)} tone={overdue ? 'danger' : undefined}>
          {overdue ? <Line label="Просрочено" value={som(summary.overdue)} tone="danger" /> : <Line label="Просрочено" value="нет" />}
          {debt ? <Line label="Неоплаченных начислений" value={debt.unpaid_count} /> : null}
          <p>{nextDue ? <>Ближайший срок: {nextDue.due_lesson ? `${nextDue.due_lesson}-й урок месяца №${nextDue.month_number ?? ''} (сейчас ${nextDue.lessons_used})`
            : formatDate(nextDue.due_date)}</> : 'только выставленные начисления'}</p>
        </Kpi>
        <Kpi label="Получено по договору" value={som(summary.net_received)}>
          <Line label="Зачтено в начисления" value={som(summary.allocated)} />
          <Line label="Свободный аванс" value={som(summary.credit)} />
          <details className="pt-1">
            <summary className="cursor-pointer text-brand-700">Подробнее</summary>
            <div className="mt-1 space-y-0.5">
              <Line label="Получено всего" value={som(summary.received)} />
              {nonZero(summary.refunded) ? <Line label="Возвраты денег" value={`−${som(summary.refunded)}`} /> : null}
              {nonZero(summary.reservation_received) ? <Line label="в т.ч. бронь (не повторно)" value={som(summary.reservation_received)} /> : null}
              {summary.voided_count ? <Line label={`Сторно (${summary.voided_count}), не учтено`} value={som(summary.voided)} tone="muted" /> : null}
              {nonZero(summary.adjusted) ? <Line label="Корректировки начислений" value={som(summary.adjusted)} /> : null}
            </div>
          </details>
        </Kpi>
        <Kpi label="Свободный аванс" value={som(summary.credit)}>
          <p>{nonZero(summary.credit_reserved_future) ? `на будущие начисления (прогноз) ${som(summary.credit_reserved_future)}`
            : nonZero(summary.reservation_unused) ? `в т.ч. бронь ${som(summary.reservation_unused)}` : 'получено, но не распределено'}</p>
          <div className="flex flex-wrap gap-x-3 pt-1">
            {canPay && nonZero(summary.credit_unapplied) ? (
              <button type="button" className="text-brand-700 hover:underline"
                onClick={() => run(async () => { await financeApi.applyCredit(c.id); invalidate() }, 'Аванс распределён')}>Распределить</button>
            ) : null}
            {card.payments ? <button type="button" className="text-brand-700 hover:underline" onClick={() => setCreditHistory(true)}>История аванса</button> : null}
          </div>
        </Kpi>
        <Kpi label="Осталось оплатить" value={som(summary.net_to_pay)} tone="brand">
          {summary.course_paid_in_full ? <p>курс полностью оплачен</p> : (
            <>
              <Line label="Текущий долг" value={som(summary.due_now)} />
              <Line label="Будущие начисления" value={som(futureDue)} />
              {nonZero(summary.credit) ? <Line label="Минус свободный аванс" value={`−${som(summary.credit)}`} /> : null}
            </>
          )}
        </Kpi>
      </div>

      {summary.course_paid_in_full ? (
        <p className="mt-3 rounded-xl border border-border bg-brand-50 p-3 text-sm text-brand-700" data-testid="course-paid">
          <b>Курс полностью оплачен</b>{c.final_course_price ? ` — ${som(c.final_course_price)}` : ''}. Текущий долг 0 сом, просрочки нет,
          дополнительные платежи не требуются. Добровольно внесённая сумма будет учтена как аванс.
        </p>
      ) : null}
      <p className="mt-2 text-xs text-ink-secondary" data-testid="money-breakdown">
        Получено {som(summary.net_received)} = оплачено по начислениям {som(summary.allocated)} + свободный аванс {som(summary.credit)}.
        {' '}Текущий долг {som(summary.due_now)} + будущие начисления {som(futureDue)}{nonZero(summary.credit) ? ` − аванс ${som(summary.credit)}` : ''} = осталось оплатить {som(summary.net_to_pay)}.
        {summary.voided_count ? ` Сторнировано ${summary.voided_count} платеж(а) на ${som(summary.voided)} — это отмена записи, не возврат денег.` : ''}
      </p>
      {Math.abs(moneyGap) >= 0.01 ? (
        <p role="alert" className="mt-2 flex gap-2 rounded-xl border border-warning/30 bg-warning-soft p-3 text-sm text-warning">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
          Получено не равно «зачтено + аванс» на {som(moneyGap.toFixed(2))}: удержание брони или исправление платежа. Проверьте журнал аванса.
        </p>
      ) : null}

      {summary.credit_unapplied !== '0.00' ? (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-warning/20 bg-warning-soft p-3 text-sm text-warning">
          <span>
            Свободный аванс {som(summary.credit_unapplied)} не распределён на неоплаченные начисления ({som(summary.invoices_balance)}).
            «Долг на сегодня» уже учитывает этот аванс; распределите его, чтобы начисления получили статус «Оплачено».
          </span>
          {canPay ? (
            <Button size="sm" onClick={() => run(async () => { await financeApi.applyCredit(c.id); invalidate() }, 'Аванс распределён')}>
              Распределить аванс
            </Button>
          ) : null}
        </div>
      ) : null}

      {c.pending_terms ? (
        <p className="mt-4 rounded-xl border border-warning/20 bg-warning-soft p-3 text-sm text-warning">
          Скидка ждёт согласования: итоговая стоимость {som(c.pending_terms.final_course_price)} (скидка {som(c.pending_terms.discount_amount)}).
          До решения начисления — черновики. Основание: {c.pending_terms.reason}
        </p>
      ) : null}

      {card.schedule ? (
        <Collapsible title="График оплаты по договору" id="schedule">
          <ScheduleBlock schedule={card.schedule} profile={c.id} canEdit={me.data?.can_manage_settings ?? false} />
        </Collapsible>
      ) : null}

      <Collapsible title="Начисления" id="invoices" actions={card.invoices.length ? (
        <SegmentedControl aria-label="Фильтр начислений" options={INVOICE_FILTERS} value={invoiceFilter} onChange={setInvoiceFilter} />
      ) : undefined}>
        {card.invoices.length === 0 ? <EmptyState title="Начислений нет" /> : invoices.length === 0
          ? <p className="text-sm text-ink-secondary">Нет начислений с таким статусом.</p> : (
          <DataTable rows={invoices} getRowKey={(i) => i.id} columns={[
            { key: 'num', header: 'Номер счёта', render: (i) => <span className="font-medium">{i.number}</span> },
            { key: 'what', header: 'Назначение', render: (i) => i.kind === 'COURSE' ? 'Весь курс' : `Месяц №${i.month_number ?? i.package_number}` },
            { key: 'amount', header: 'Сумма', render: (i) => <Amount value={i.amount} /> },
            { key: 'paid', header: 'Оплачено', render: (i) => <Amount value={i.amount_paid} tone="muted" /> },
            { key: 'bal', header: 'Остаток', render: (i) => <Amount value={i.balance} tone={i.status === 'OVERDUE' ? 'danger' : undefined} /> },
            { key: 'due', header: 'Срок оплаты', render: (i) => i.due_lesson ? `${i.due_lesson}-й урок (сейчас ${i.lessons_used})` : formatDate(i.due_date) },
            { key: 'st', header: 'Статус', render: (i) => <div className="flex flex-wrap gap-1"><InvoiceStatusBadge status={i.status} label={i.status_display} />
              {i.stage === 'deadline' || (i.stage === 'overdue' && i.status !== 'OVERDUE') ? <StageBadge stage={i.stage} /> : null}</div> },
            { key: 'act', header: 'Действия', render: (i) => <Button size="sm" variant="ghost" onClick={() => setOpenInvoice(i)}>Подробнее</Button> },
          ]} />
        )}
      </Collapsible>

      {card.payments ? (
        <Collapsible title="Платежи и чеки" id="payments">
          {card.payments.length === 0 ? <EmptyState title="Платежей пока нет" /> : (
            <OperationsTable payments={card.payments} canPay={canPay} onReverse={setReversing} />
          )}
        </Collapsible>
      ) : null}

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Card title="Условия договора">
          {canTerms ? (
            <Button size="sm" variant="secondary" className="mb-3" leftIcon={<Pencil className="size-4" />} onClick={() => setTerms(true)}>
              Редактировать договор</Button>
          ) : null}
          <dl className="grid grid-cols-1 gap-x-4 gap-y-2 text-sm min-[420px]:grid-cols-2">
            <Term label="Стандартная стоимость курса" value={som(c.standard_course_price)} />
            <Term label="Итоговая стоимость курса" value={som(c.final_course_price)} />
            <Term label="Скидка" value={c.discount_enabled ? som(c.discount_amount) : 'нет'} />
            <Term label="Причина скидки" value={c.discount_reason || '—'} />
            <Term label="Способ оплаты" value={c.payment_mode_display} />
            <Term label="Учёт брони" value={c.reservation_allocation_display} />
            <Term label="Стоимость учебного месяца" value={c.month_price ? som(c.month_price) : '—'} />
            <Term label="Занятий в месяце" value={c.lessons_per_month ? `${c.lessons_per_month} уроков ${c.subject_name ?? ''}` : '—'} />
            <Term label="Срок оплаты" value={c.deadline_lessons ? `не позднее ${c.deadline_lessons}-го урока месяца` : '—'} />
            <Term label="Начало обучения" value={formatDate(c.start_date)} />
            <Term label="Продолжительность курса" value={c.duration_months && c.lessons_per_month
              ? `${c.duration_months * c.lessons_per_month} уроков ${c.subject_name ?? ''}` : 'без срока'} />
            <Term label="Учебных месяцев" value={c.duration_months ? String(c.duration_months) : 'без срока'} />
          </dl>
          {c.special_terms ? <p className="mt-3 text-sm text-ink-secondary">Особые условия: {c.special_terms}</p> : null}
        </Card>
        <Card title="Бронь">
          <ReservationBlock reservations={card.reservations} canPay={canPay} onPay={setReservationPay} />
        </Card>
      </div>

      <Collapsible title="Обучение и начисления" id="study">
        <div className="space-y-3">
          {card.progress ? <ProgressBlock progress={card.progress} subject={c.subject_name ?? 'IT'} /> : null}
          <LessonCount profile={c.id} canFix={me.data?.can_manage_settings ?? false} />
        </div>
      </Collapsible>

      <Collapsible title={c.is_course ? 'Финансовые пакеты договора (по ним начисления)' : 'Учебные месяцы'} id="packages">
        {card.months.length === 0 ? <EmptyState title="Месяцев пока нет" /> : (
          <DataTable rows={card.months} getRowKey={(m) => m.id} columns={[
            { key: 'n', header: 'Пакет', render: (m) => <span className="font-medium">№{m.month_number ?? m.number}</span> },
            { key: 'st', header: 'Статус', render: (m) => {
              const st = m.status === 'ACTIVE' && c.status === 'PAUSED' ? { label: 'Приостановлен', tone: 'warning' as const } : PACKAGE_STATUS[m.status]
              return <Badge tone={st.tone}>{st.label}</Badge>
            } },
            { key: 'l', header: 'Уроки IT', render: (m) => (
              <div className="min-w-24">
                <span className="text-sm">{m.lessons_used} из {m.lessons_total}</span>
                <div className="mt-1 h-1.5 w-20 overflow-hidden rounded-full bg-surface-hover" aria-hidden>
                  <div className="h-full rounded-full bg-brand-500" style={{ width: `${Math.min(100, Math.round((m.lessons_used / Math.max(m.lessons_total, 1)) * 100))}%` }} />
                </div>
              </div>
            ) },
            { key: 'inv', header: 'Начислено', render: (m) => m.invoice ? (
              <span><Amount value={m.invoice.amount} /><span className="block text-xs text-ink-secondary">{m.invoice.number}</span></span>
            ) : m.course_share ? (
                <span className="text-sm" title={`Доля начисления «Весь курс» ${m.course_share.number}, не отдельное начисление`}>
                  <Amount value={m.course_share.amount} />
                  <span className="block text-xs text-ink-secondary">
                    {m.course_share.paid_in_full ? 'оплачен предоплатой курса' : `доля курса, оплачено ${som(m.course_share.paid)}`}
                  </span>
                </span>
              ) : <span className="text-sm text-ink-secondary">оплачен по договору</span> },
            { key: 'paid', header: 'Оплачено', render: (m) => m.invoice
              ? <Amount value={m.invoice.amount_paid ?? (Number(m.invoice.amount) - Number(m.invoice.balance)).toFixed(2)} tone="muted" />
              : m.course_share ? <Amount value={m.course_share.paid} tone="muted" /> : '—' },
            { key: 'bal', header: 'Остаток', render: (m) => m.invoice ? <Amount value={m.invoice.balance} /> : '—' },
            { key: 'start', header: 'Начало', render: (m) => formatDate(m.started_on) },
            { key: 'end', header: 'Завершение', render: (m) => formatDate(m.completed_on) },
          ]} />
        )}
      </Collapsible>

      {card.contacts ? (
        <Collapsible title="Контакты с родителями" id="contacts" actions={canPay ? (
          <Button size="sm" variant="secondary" leftIcon={<Phone className="size-4" />} onClick={() => setContact(true)}>Новый контакт</Button>
        ) : undefined}>
          {card.contacts.length === 0 ? <p className="text-sm text-ink-secondary">Контактов не было.</p> : (
            <ul className="space-y-2">
              {card.contacts.map((x) => (
                <li key={x.id} className="card p-3 text-sm">
                  <p className="font-medium">{formatDateTime(x.contacted_at)} · {x.channel_display} · {x.result_display}</p>
                  <p className="text-ink-secondary">Ответственный: {x.staff_name}{x.comment ? ` — ${x.comment}` : ''}
                    {x.promised_payment_date ? ` · обещал оплатить ${formatDate(x.promised_payment_date)}` : ''}
                    {x.next_contact_date ? ` · следующий контакт ${formatDate(x.next_contact_date)}` : ''}</p>
                </li>
              ))}
            </ul>
          )}
        </Collapsible>
      ) : null}

      {contact ? <ContactModal profile={c.id} student={c.student_name} onClose={() => setContact(false)} /> : null}
      {terms ? <TermsModal card={card} onClose={() => setTerms(false)} /> : null}
      {reservationPay ? <ReservationPayModal reservation={reservationPay} onClose={() => setReservationPay(null)} /> : null}
      {creditHistory ? <CreditDrawer profile={c.id} onClose={() => setCreditHistory(false)} /> : null}
      {openInvoice ? <InvoiceDrawer invoice={openInvoice} payments={card.payments ?? []} onClose={() => setOpenInvoice(null)} /> : null}
      <ReasonModal isOpen={reversing !== null} title="Сторно платежа" tone="danger" confirmLabel="Сторнировать"
        description="Сторно — отмена ошибочной записи, а не возврат денег. Платёж не удаляется: он помечается отменённым, распределения возвращаются, чек аннулируется. Операция попадёт в журнал."
        onClose={() => setReversing(null)}
        onConfirm={async (reason) => {
          const ok = await run(() => financeApi.reversePayment(reversing!.id, reason), 'Платёж сторнирован')
          if (ok) invalidate()
          return ok
        }} />
    </div>
  )
}

/** Журнал свободного аванса: поступления, распределения на начисления, сторно, возвраты. */
function CreditDrawer({ profile, onClose }: { profile: number; onClose: () => void }) {
  const query = useQuery({ queryKey: [...FINANCE_KEY, 'credit', profile], queryFn: () => financeApi.credit(profile) })
  return (
    <Drawer isOpen onClose={onClose} side="right" size="lg" title="История свободного аванса">
      {query.isLoading ? <p className="text-sm text-ink-secondary">Загрузка…</p> : !query.data ? <p className="text-sm text-danger">Не удалось загрузить.</p> : (
        <div className="space-y-3 text-sm">
          <p>Свободный аванс сейчас: <b>{som(query.data.balance)}</b>. Распределение аванса не создаёт новых денег — оно переносит уже полученные на начисление.</p>
          {query.data.entries.length === 0 ? <p className="text-ink-secondary">Записей нет.</p> : (
            <ul className="divide-y divide-border rounded-xl border border-border">
              {query.data.entries.map((e) => (
                <li key={e.id} className="flex items-start justify-between gap-3 p-2">
                  <span><span className="font-medium">{e.kind_display}</span>
                    <span className="block text-xs text-ink-secondary">{formatDateTime(e.created_at)}{e.payment ? ` · платёж №${e.payment}` : ''}{e.comment ? ` · ${e.comment}` : ''}</span></span>
                  <span className={cn('whitespace-nowrap tabular-nums', Number(e.amount) < 0 ? 'text-ink-secondary' : 'text-brand-700')}>
                    {Number(e.amount) > 0 ? '+' : ''}{som(e.amount)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Drawer>
  )
}

/** Подробности начисления: период, сроки, корректировки и платежи, которыми оно оплачено. */
function InvoiceDrawer({ invoice, payments, onClose }: { invoice: Invoice; payments: Payment[]; onClose: () => void }) {
  const query = useQuery({ queryKey: [...FINANCE_KEY, 'invoice', invoice.id], queryFn: () => financeApi.invoice(invoice.id) })
  const detail = query.data
  const byPayment = new Map(payments.map((p) => [p.id, p]))
  return (
    <Drawer isOpen onClose={onClose} side="right" size="lg" title={`Начисление ${invoice.number}`}>
      <div className="space-y-4 text-sm">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2">
          <Term label="Назначение" value={invoice.kind === 'COURSE' ? 'Весь курс (предоплата)' : `Учебный месяц №${invoice.month_number ?? invoice.package_number}`} />
          <Term label="Статус" value={invoice.status_display} />
          <Term label="Период начисления" value={formatDate(invoice.period_date)} />
          <Term label="Выставлено" value={formatDate(invoice.issue_date)} />
          <Term label="Срок оплаты" value={invoice.due_lesson ? `${invoice.due_lesson}-й урок месяца (сейчас ${invoice.lessons_used} из ${invoice.lessons_total})` : formatDate(invoice.due_date)} />
          <Term label="Просрочено с" value={formatDate(invoice.overdue_since)} />
          <Term label="Сумма" value={som(invoice.amount)} />
          <Term label="Оплачено" value={som(invoice.amount_paid)} />
          <Term label="Корректировки" value={som(invoice.amount_adjusted)} />
          <Term label="Остаток" value={som(invoice.balance)} />
        </dl>
        <div>
          <h3 className="mb-1 font-semibold">Платежи по начислению</h3>
          {!detail ? <p className="text-ink-secondary">{query.isError ? 'Не удалось загрузить.' : 'Загрузка…'}</p>
            : detail.allocations.length === 0 ? <p className="text-ink-secondary">Оплат не было.</p> : (
              <ul className="divide-y divide-border rounded-xl border border-border">
                {detail.allocations.map((a) => {
                  const p = byPayment.get(a.payment)
                  return (
                    <li key={a.id} className="flex items-center justify-between gap-2 p-2">
                      <span>
                        <Link to={`/finance/payments/${a.payment}`} className="text-brand-700 hover:underline">Платёж №{a.payment}</Link>
                        {p ? <span className="text-ink-secondary"> · {formatDate(p.received_date)} · {operationType(p)}</span> : null}
                        {a.status !== 'ACTIVE' ? <span className="block text-xs text-ink-muted">сторно распределения{a.reverse_reason ? `: ${a.reverse_reason}` : ''}</span> : null}
                      </span>
                      <span className={cn(a.status !== 'ACTIVE' && 'text-ink-muted line-through')}><Amount value={a.amount} /></span>
                    </li>
                  )
                })}
              </ul>
            )}
        </div>
        {detail?.adjustments.length ? (
          <div>
            <h3 className="mb-1 font-semibold">Корректировки</h3>
            <ul className="space-y-1">
              {detail.adjustments.map((a) => (
                <li key={a.id} className={cn(a.status !== 'APPLIED' && 'text-ink-muted line-through')}>
                  {formatDate(a.effective_date)} · {som(a.amount)} · {a.reason}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </Drawer>
  )
}

function Term({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="text-ink-secondary">{label}</dt>
      <dd className="text-ink">{value}</dd>
    </>
  )
}

function TermsModal({ card, onClose }: { card: ContractCard; onClose: () => void }) {
  const c = card.contract
  const [discount, setDiscount] = useState(c.discount_enabled)
  const [price, setPrice] = useState(c.final_course_price ?? '')
  const [reason, setReason] = useState(c.discount_reason)
  const invalidate = useInvalidateFinance()
  const { run, busy } = useRunner()
  const target = discount ? Number(String(price).replace(',', '.')) : Number(c.standard_course_price ?? 0)
  const newFuture = Number.isFinite(target) && String(price) !== '' ? target - Number(card.summary.invoiced) : null
  return (
    <Modal isOpen onClose={onClose} title="Итоговая стоимость курса">
      <p className="mb-3 text-sm text-ink-secondary">Новая цена действует на будущие учебные месяцы. Уже выставленные начисления и
        проведённые платежи не меняются. Стандартная стоимость — {som(c.standard_course_price)}.</p>
      <label className="flex items-center gap-2 text-sm font-medium">
        <input type="checkbox" checked={discount} onChange={(e) => setDiscount(e.target.checked)} /> Скидка предоставлена
      </label>
      {discount ? (
        <div className="mt-3 space-y-3">
          <Field label="Итоговая стоимость курса" htmlFor="tm-price" required>
            <Input id="tm-price" inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} />
          </Field>
          <Field label="Причина скидки" htmlFor="tm-reason" required>
            <Textarea id="tm-reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
          </Field>
        </div>
      ) : null}
      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-1 rounded-lg bg-surface-muted p-3 text-sm" data-testid="terms-impact">
        <dt className="text-ink-secondary">Уже выставлено (не меняется)</dt><dd className="text-right tabular-nums">{som(card.summary.invoiced)}</dd>
        <dt className="text-ink-secondary">Будущие начисления</dt>
        <dd className="text-right tabular-nums">{som(card.summary.future)}{newFuture !== null && newFuture !== Number(card.summary.future ?? 0)
          ? <> → <b>{som(newFuture.toFixed(2))}</b></> : null}</dd>
      </dl>
      {newFuture !== null && newFuture < 0 ? <p className="mt-2 text-sm text-danger">Итоговая стоимость меньше уже начисленного — нужна корректировка начислений.</p> : null}
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Отмена</Button>
        <Button isLoading={busy} onClick={async () => {
          const ok = await run(() => financeApi.courseTerms(c.id, {
            discount_enabled: discount, final_course_price: discount ? price : null, reason,
          }), 'Условия сохранены')
          if (ok) { invalidate(); onClose() }
        }}>Сохранить</Button>
      </div>
    </Modal>
  )
}

function ReservationPayModal({ reservation, onClose }: { reservation: Reservation; onClose: () => void }) {
  const options = useFinanceOptions()
  const invalidate = useInvalidateFinance()
  const { run, busy } = useRunner()
  const [key] = useState(newIdempotencyKey)
  const [amount, setAmount] = useState(reservation.expected_amount)
  const [method, setMethod] = useState('cash')
  const [date, setDate] = useState(today())
  return (
    <Modal isOpen onClose={onClose} title="Оплата брони">
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Сумма" htmlFor="rp-amount"><Input id="rp-amount" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
        <Field label="Способ" htmlFor="rp-method">
          <Select id="rp-method" value={method} onChange={(e) => setMethod(e.target.value)} options={options.data?.payment_methods ?? []} />
        </Field>
        <Field label="Дата" htmlFor="rp-date"><Input id="rp-date" type="date" value={date} max={today()} onChange={(e) => setDate(e.target.value)} /></Field>
      </div>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Отмена</Button>
        <Button isLoading={busy} onClick={async () => {
          const ok = await run(() => financeApi.payReservation(reservation.id, { amount, received_date: date, method }, key), 'Бронь оплачена, чек выдан')
          if (ok) { invalidate(); onClose() }
        }}>Принять</Button>
      </div>
    </Modal>
  )
}

/** Почему посещений больше, чем засчитано уроков: учебный месяц считается только
 * по проведённым урокам приоритетного предмета с даты начала договора. */
const REASON_TONE: Record<string, string> = { counted: 'text-brand-700', before_contract: 'text-warning' }

/** Каждое посещение — засчитано ли оно в учебные месяцы и почему (данные — backend `lesson_breakdown`). */
function LessonCount({ profile, canFix }: { profile: number; canFix: boolean }) {
  const [open, setOpen] = useState(false)
  const [fixing, setFixing] = useState(false)
  const query = useQuery({ queryKey: [...FINANCE_KEY, 'lessons', profile], queryFn: () => financeApi.lessonBreakdown(profile) })
  const data = query.data
  if (!data) return null
  const reasons = Object.entries(data.totals).filter(([key]) => key !== 'counted')
  const before = data.priority_before_contract
  return (
    <div className="mt-4 rounded-xl border border-border bg-surface p-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p>
          Посещений (присутствовал / опоздал): <b>{data.attended}</b> · засчитано в учебные месяцы
          {data.priority_subject ? ` (${data.priority_subject})` : ''}: <b>{data.counted}</b>
          {reasons.map(([key, n]) => (
            <span key={key} className="text-ink-secondary"> · {data.lessons.find((l) => l.reason === key)?.reason_display}: {n}</span>
          ))}
        </p>
        {data.lessons.length ? <Button size="sm" variant="ghost" onClick={() => setOpen(!open)}>{open ? 'Скрыть' : 'Разбор посещений'}</Button> : null}
      </div>
      {before.count ? (
        <p className="mt-2 text-warning">
          {before.count} проведённых уроков {data.priority_subject ?? ''} до даты начала договора ({formatDate(data.contract_start)}), первый — {formatDate(before.first_date)}.
          Если дата начала указана ошибочно, исправьте её — уроки будут засчитаны по обычным правилам.
          {canFix ? <Button size="sm" variant="ghost" className="ml-1" onClick={() => setFixing(true)}>Исправить дату начала</Button> : null}
        </p>
      ) : null}
      {open ? (
        <div className="relative mt-3 overflow-x-auto">
          <table className="w-full min-w-[640px] text-left">
            <thead className="text-xs text-ink-secondary">
              <tr><th className="py-1 pr-3">Дата</th><th className="pr-3">Предмет</th><th className="pr-3">Группа</th>
                <th className="pr-3">Статус посещения</th><th className="pr-3">Дата договора</th><th>Причина учёта или исключения</th></tr>
            </thead>
            <tbody className="divide-y divide-border">
              {data.lessons.map((l) => (
                <tr key={l.lesson}>
                  <td className="py-1 pr-3 whitespace-nowrap">{formatDate(l.date)}</td>
                  <td className="pr-3">{l.subject ?? '—'}</td>
                  <td className="pr-3">{l.group}</td>
                  <td className="pr-3">{l.attendance_display}{l.lesson_status !== 'completed' ? ` · урок: ${l.lesson_status_display}` : ''}</td>
                  <td className="pr-3 whitespace-nowrap">{formatDate(l.contract_start)}</td>
                  <td className={REASON_TONE[l.reason] ?? 'text-ink-secondary'}>
                    {l.reason_display}{l.month_number ? ` (месяц ${l.month_number})` : ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {fixing ? <StartDateModal profile={profile} suggested={before.first_date} onClose={() => setFixing(false)} /> : null}
    </div>
  )
}

function StartDateModal({ profile, suggested, onClose }: { profile: number; suggested: string | null; onClose: () => void }) {
  const [date, setDate] = useState(suggested ?? '')
  const [reason, setReason] = useState('')
  const invalidate = useInvalidateFinance()
  const { run, busy } = useRunner()
  return (
    <Modal isOpen onClose={onClose} title="Исправить дату начала договора">
      <p className="mb-3 text-sm text-ink-secondary">
        Посещаемость, платежи и суммы начислений не меняются. Уроки приоритетного предмета с новой даты засчитываются
        в учебные месяцы; другие предметы и отменённые уроки — нет. Изменение записывается в журнал операций.
      </p>
      <Field label="Новая дата начала" htmlFor="sd-date" required>
        <Input id="sd-date" type="date" value={date} max={today()} onChange={(e) => setDate(e.target.value)} />
      </Field>
      <Field label="Основание" htmlFor="sd-reason" required className="mt-3">
        <Textarea id="sd-reason" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Отмена</Button>
        <Button isLoading={busy} disabled={!date || !reason.trim()} onClick={async () => {
          const ok = await run(() => financeApi.changeStartDate(profile, { start_date: date, reason: reason.trim() }), 'Дата начала исправлена')
          if (ok) { invalidate(); onClose() }
        }}>Сохранить</Button>
      </div>
    </Modal>
  )
}
