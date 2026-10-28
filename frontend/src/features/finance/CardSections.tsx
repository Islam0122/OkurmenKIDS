import { useState } from 'react'
import { AlertTriangle, History, PencilLine, Printer } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'

import { financeApi } from '@/api/finance'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Drawer } from '@/components/ui/Drawer'
import { Input } from '@/components/ui/Input'
import { Menu } from '@/components/ui/Menu'
import type { MenuItem } from '@/components/ui/Menu'
import { Modal } from '@/components/ui/Modal'
import { Textarea } from '@/components/ui/Textarea'
import { Field } from '@/features/worklog/formUi'
import type {
  MonthPlanBody, MonthPlanResult, MonthUiStatus, Payment, PaymentSchedule, Reservation, ScheduleMonth,
} from '@/types/finance'
import { cn } from '@/utils/cn'

import { MonthEditDrawer, MonthHistoryDrawer, MonthStatusBadge } from './MonthEditPanel'
import { Amount, formatDate, som, useInvalidateFinance, useRunner } from './ui'

/** Тип операции для таблицы: бронь, предоплата, платёж, возврат. */
export function operationType(p: Payment): string {
  if (p.kind === 'refund') return 'Возврат'
  if (p.purpose === 'reservation') return 'Бронь'
  if (p.purpose === 'prepayment') return 'Предоплата'
  return 'Платёж'
}

function StatusBadge({ p }: { p: Payment }) {
  return p.status === 'void' ? <Badge tone="muted">Сторно</Badge> : <Badge tone="success">Проведён</Badge>
}

function paidFor(p: Payment): string {
  const chain = [
    p.replaced_by?.length ? `заменён платежами ${p.replaced_by.map((id) => `№${id}`).join(', ')}` : '',
    p.replaces?.length ? `взамен сторнированного ${p.replaces.map((id) => `№${id}`).join(', ')}` : '',
  ].filter(Boolean).join('; ')
  if (p.status === 'void') return chain || 'не учитывается в поступлениях'
  const active = p.allocations.filter((a) => a.status === 'ACTIVE')
  const where = active.length ? `на ${active.map((a) => a.invoice_number).join(', ')}` : p.kind === 'payment' ? 'аванс' : ''
  return [where, chain].filter(Boolean).join(' · ')
}

/** «Платежи и чеки»: одна операция — одна строка (на телефоне — карточка).
 * Бронь — не отдельная строка, а тип операции её платежа. Сторно — отмена записи, не возврат денег. */
export function OperationsTable({ payments, canPay, onReverse }: {
  payments: Payment[]
  canPay: boolean
  onReverse: (p: Payment) => void
}) {
  const [allocation, setAllocation] = useState<Payment | null>(null)
  const navigate = useNavigate()
  const actions = (p: Payment, wrap = false) => {
    const items: MenuItem[] = []
    if (p.kind === 'payment') items.push({ key: 'alloc', label: 'Распределение', onClick: () => setAllocation(p) })
    if (p.receipt) items.push({ key: 'receipt', label: 'Открыть чек', onClick: () => navigate(`/finance/receipts/${p.receipt!.id}`) })
    if (canPay && p.status === 'confirmed') items.push({ key: 'reverse', label: 'Сторно', tone: 'danger', onClick: () => onReverse(p) })
    return (
      <div className={cn('flex items-center gap-1 whitespace-nowrap', wrap ? 'flex-wrap' : 'justify-end')}>
        <Link to={`/finance/payments/${p.id}`} className="inline-flex h-8 items-center rounded-lg px-2 text-sm text-brand-700 hover:bg-brand-50">
          Открыть
        </Link>
        <Menu items={items} label={`Действия: платёж №${p.id}`} />
      </div>
    )
  }
  const receipt = (p: Payment) => p.receipt ? (
    <Link to={`/finance/receipts/${p.receipt.id}`} className="inline-flex items-center gap-1 whitespace-nowrap text-sm text-brand-700 hover:underline">
      <Printer className="size-4" aria-hidden />{p.receipt.number}
    </Link>
  ) : '—'
  return (
    <>
      <div className="card relative hidden overflow-x-auto 2xl:block">
        <table className="data-table min-w-[900px] [&_td]:px-2 [&_th]:px-2" aria-label="Платежи и чеки">
          <thead>
            <tr>
              {['Дата', 'Тип операции', 'Назначение', 'Сумма', 'Способ оплаты', 'Статус', 'Кто принял', 'Номер чека', 'Действия'].map((h) => (
                <th key={h} scope="col" className={cn('whitespace-nowrap', h === 'Действия' && 'text-right')}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {payments.map((p) => (
              <tr key={p.id} className="align-top">
                <td className="whitespace-nowrap">{formatDate(p.received_date)}</td>
                <td className="whitespace-nowrap font-medium">{operationType(p)}</td>
                <td><span className="block max-w-40 truncate text-sm text-ink-secondary" title={paidFor(p)}>{paidFor(p) || '—'}</span></td>
                <td className={cn('whitespace-nowrap', p.status === 'void' && 'text-ink-muted line-through')}
                  title={p.status === 'void' ? 'Сторнировано — не учитывается в поступлениях' : undefined}>
                  <Amount value={p.kind === 'refund' ? `-${p.amount}` : p.amount} tone={p.status === 'void' ? 'muted' : undefined} />
                </td>
                <td>{p.method_display}</td>
                <td><StatusBadge p={p} /></td>
                <td>{p.created_by_name ?? '—'}</td>
                <td>{receipt(p)}</td>
                <td className="text-right">{actions(p)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="grid gap-2 md:grid-cols-2 2xl:hidden" aria-label="Платежи и чеки">
        {payments.map((p) => (
          <li key={p.id} className="card p-3 text-sm">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="font-medium">{operationType(p)} · {formatDate(p.received_date)}</p>
                <p className="text-xs text-ink-secondary">{paidFor(p)}</p>
              </div>
              <span className={cn(p.status === 'void' && 'line-through')}><Amount value={p.kind === 'refund' ? `-${p.amount}` : p.amount} /></span>
            </div>
            <dl className="mt-2 grid grid-cols-2 gap-1 text-xs">
              <dt className="text-ink-secondary">Способ</dt><dd>{p.method_display}</dd>
              <dt className="text-ink-secondary">Статус</dt><dd><StatusBadge p={p} /></dd>
              <dt className="text-ink-secondary">Принял</dt><dd>{p.created_by_name ?? '—'}</dd>
              <dt className="text-ink-secondary">Чек</dt><dd>{receipt(p)}</dd>
            </dl>
            <div className="mt-2">{actions(p, true)}</div>
          </li>
        ))}
      </ul>
      {allocation ? <AllocationDrawer payment={allocation} onClose={() => setAllocation(null)} /> : null}
    </>
  )
}

/** Куда распределены деньги платежа: действующие и сторнированные распределения, нераспределённый остаток. */
function AllocationDrawer({ payment, onClose }: { payment: Payment; onClose: () => void }) {
  return (
    <Drawer isOpen onClose={onClose} side="right" title={`Распределение платежа №${payment.id}`}>
      <div className="space-y-3 text-sm">
        <p>{operationType(payment)} от {formatDate(payment.received_date)} на <b>{som(payment.amount)}</b>
          {payment.status === 'void' ? ' — сторнирован, в поступлениях не учитывается.' : '.'}</p>
        {payment.allocations.length === 0 ? <p className="text-ink-secondary">Платёж не распределён на начисления.</p> : (
          <ul className="divide-y divide-border rounded-xl border border-border">
            {payment.allocations.map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-2 p-2">
                <span>{a.invoice_number}{a.status !== 'ACTIVE' ? <span className="ml-1 text-xs text-ink-muted">(сторно распределения)</span> : null}</span>
                <span className={cn(a.status !== 'ACTIVE' && 'text-ink-muted line-through')}><Amount value={a.amount} /></span>
              </li>
            ))}
          </ul>
        )}
        {payment.status === 'confirmed' && payment.kind === 'payment' ? (
          <p>Свободный остаток платежа (аванс): <b>{som(payment.unallocated)}</b></p>
        ) : null}
        <Link to={`/finance/payments/${payment.id}`} className="inline-flex text-brand-700 hover:underline">Открыть платёж</Link>
      </div>
    </Drawer>
  )
}

/** Бронь: оплаченная — тот же платёж (сколько засчитано в начисления, сколько авансом), не вторые деньги. */
export function ReservationBlock({ reservations, canPay, onPay }: {
  reservations: Reservation[]
  canPay: boolean
  onPay: (r: Reservation) => void
}) {
  const [editing, setEditing] = useState<Reservation | null>(null)
  const [cancelling, setCancelling] = useState<Reservation | null>(null)
  if (reservations.length === 0) return <p className="text-sm text-ink-secondary">Брони нет.</p>
  return (
    <ul className="space-y-3 text-sm">
      {reservations.map((r) => (
        <li key={r.id}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-medium">
              {som(r.expected_amount)} · {r.status === 'PAID' ? 'оплачена' : r.status === 'PENDING' ? 'ожидает оплаты' : 'отменена'}
              {r.reserved_until ? ` · до ${formatDate(r.reserved_until)}` : ''}
            </span>
            <div className="flex gap-1">
              {r.status === 'PENDING' && canPay ? (
                <>
                  <Button size="sm" variant="secondary" onClick={() => onPay(r)}>Принять оплату брони</Button>
                  <Button size="sm" variant="ghost" onClick={() => setEditing(r)}>Исправить</Button>
                </>
              ) : null}
              {r.status !== 'CANCELLED' && canPay ? <Button size="sm" variant="ghost" onClick={() => setCancelling(r)}>Отменить</Button> : null}
            </div>
          </div>
          {r.payment ? (
            <p className="mt-1 text-ink-secondary">
              Оплачена платежом <Link to={`/finance/payments/${r.payment}`} className="text-brand-700 hover:underline">№{r.payment}</Link>
              {r.paid_date ? ` от ${formatDate(r.paid_date)}` : ''}{r.receipt_number ? ` (чек ${r.receipt_number})` : ''}: получено {som(r.paid_amount)},
              засчитано в начисления {som(r.paid_used)}{r.paid_unused !== null ? `, осталось авансом ${som(r.paid_unused)}` : ''}.
              Это тот же платёж — в «Получено по договору» он учтён один раз.
            </p>
          ) : null}
          {r.payment ? (
            <div className="mt-1 flex flex-wrap gap-3 text-sm">
              <Link to={`/finance/payments/${r.payment}`} className="text-brand-700 hover:underline">Открыть платёж</Link>
              {r.receipt ? <Link to={`/finance/receipts/${r.receipt}`} className="text-brand-700 hover:underline">Открыть чек</Link> : null}
            </div>
          ) : null}
          {r.cancel_reason ? <p className="mt-1 text-xs text-ink-secondary">Отменена: {r.cancel_reason}</p> : null}
        </li>
      ))}
      {editing ? <ReservationEditModal reservation={editing} onClose={() => setEditing(null)} /> : null}
      {cancelling ? <ReservationCancelModal reservation={cancelling} onClose={() => setCancelling(null)} /> : null}
    </ul>
  )
}

function ReservationEditModal({ reservation, onClose }: { reservation: Reservation; onClose: () => void }) {
  const [amount, setAmount] = useState(reservation.expected_amount)
  const [until, setUntil] = useState(reservation.reserved_until ?? '')
  const [reason, setReason] = useState('')
  const invalidate = useInvalidateFinance()
  const { run, busy } = useRunner()
  return (
    <Modal isOpen onClose={onClose} title="Исправить бронь">
      <div className="space-y-3">
        <Field label="Сумма брони, сом" htmlFor="re-amount"><Input id="re-amount" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
        <Field label="Бронь до" htmlFor="re-until"><Input id="re-until" type="date" value={until} onChange={(e) => setUntil(e.target.value)} /></Field>
        <Field label="Причина" htmlFor="re-reason" required><Textarea id="re-reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>Отмена</Button>
          <Button isLoading={busy} disabled={!reason.trim()} onClick={async () => {
            if (await run(() => financeApi.editReservation(reservation.id, { expected_amount: amount.replace(',', '.'),
              reserved_until: until || null, reason: reason.trim() }), 'Бронь исправлена')) { invalidate(); onClose() }
          }}>Сохранить</Button>
        </div>
      </div>
    </Modal>
  )
}

function ReservationCancelModal({ reservation, onClose }: { reservation: Reservation; onClose: () => void }) {
  const [reason, setReason] = useState('')
  const invalidate = useInvalidateFinance()
  const { run, busy } = useRunner()
  return (
    <Modal isOpen onClose={onClose} title="Отменить бронь">
      <p className="text-sm text-ink-secondary">
        {reservation.payment
          ? `Бронь оплачена: платёж и чек не удаляются, деньги платежа (${som(reservation.paid_amount)}) остаются в договоре.
            ${reservation.paid_used && reservation.paid_used !== '0.00' ? `Из них ${som(reservation.paid_used)} уже зачтено в начисления — это зачтение не отменяется. ` : ''}Неиспользованная часть останется авансом; возврат денег — отдельной операцией. Если деньги не поступали — аннулируйте (сторнируйте) платёж брони на странице платежа.`
          : 'Неоплаченная бронь будет отменена. Денежных операций по ней не было.'}
      </p>
      <Field label="Причина" htmlFor="rc-reason" required className="mt-3">
        <Textarea id="rc-reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Назад</Button>
        <Button variant="danger" isLoading={busy} disabled={!reason.trim()} onClick={async () => {
          if (await run(() => financeApi.cancelReservation(reservation.id, reason.trim()), 'Бронь отменена')) { invalidate(); onClose() }
        }}>Отменить бронь</Button>
      </div>
    </Modal>
  )
}

const STATE: Record<string, string> = {
  invoiced: 'выставлен', planned: 'оплачен по договору', future: 'Будет выставлен',
  prepaid: 'оплачен предоплатой курса', course_due: 'ждёт оплаты «Весь курс»',
}

const LEGACY_STATUS: Partial<Record<string, MonthUiStatus>> = {
  OPEN: 'awaiting', PARTIALLY_PAID: 'partial', PAID: 'paid', OVERDUE: 'overdue', DRAFT: 'draft',
}

function due(m: ScheduleMonth): string {
  if (m.state !== 'invoiced') return '—'
  if (m.due_lesson) return `${m.due_lesson}-й урок (сейчас ${m.lessons_used ?? 0})`
  return formatDate(m.due_date ?? null)
}

/** Значения строки графика: стандарт, план и начисление — три разные суммы. Старые ответы без
 * `standard`/`plan`/`charge` (договор без плана) показываются по прежним полям. */
function view(m: ScheduleMonth) {
  const invoiced = m.state === 'invoiced'
  const status: MonthUiStatus | null = m.ui_status ?? (invoiced && m.status ? LEGACY_STATUS[m.status] ?? null
    : m.state === 'future' ? 'future' : null)
  return {
    standard: m.standard ?? m.standard_price,
    plan: m.plan ?? m.plan_amount ?? (invoiced || m.state === 'future' ? m.amount : null),
    charge: invoiced ? (m.charge ?? m.amount) : m.kind === 'COURSE' ? m.amount : null,
    paid: m.allocated ?? m.paid,
    balance: invoiced ? m.balance : null,
    status,
  }
}

function MonthStatus({ m }: { m: ScheduleMonth }) {
  const v = view(m)
  if (m.state === 'prepaid') return <span className="flex flex-col items-start gap-1"><MonthStatusBadge status="paid" /><span className="text-xs text-ink-secondary">{STATE.prepaid}</span></span>
  if (m.state === 'course_due') return <span className="text-sm">{STATE.course_due}</span>
  if (m.state === 'planned') return <span className="text-sm">{STATE.planned}</span>
  return v.status ? <MonthStatusBadge status={v.status} /> : <span>{STATE[m.state]}</span>
}

function Flags({ m }: { m: ScheduleMonth }) {
  return (
    <>
      {m.manual ? <span className="ml-1 inline-flex items-center text-xs text-info" title="Суммы месяца изменены вручную — см. историю">
        <PencilLine className="size-3.5" aria-hidden /><span className="sr-only">изменено вручную</span></span> : null}
      {m.plan_mismatch ? <span className="block text-xs text-warning">план ≠ начисление</span> : null}
    </>
  )
}

/** График оплаты: стандарт, план и фактическое начисление месяца отдельно, оплачено, остаток, срок,
 * статус (по актуальным данным backend), действия строки; итоги стоимости курса и их сверка. */
export function ScheduleBlock({ schedule, profile, canEdit }: { schedule: PaymentSchedule; profile?: number; canEdit?: boolean }) {
  const [editingPlan, setEditingPlan] = useState(false)
  const [editing, setEditing] = useState<ScheduleMonth | null>(null)
  const [history, setHistory] = useState<number | null | undefined>(undefined)
  const rows = schedule.months.map((m) => ({ m, v: view(m) }))
  const key = (m: ScheduleMonth) => `${m.month_number}-${m.invoice ?? 'p'}-${m.state}`
  const actions = (m: ScheduleMonth) => {
    const items: MenuItem[] = []
    if (canEdit && profile && m.editable && !m.editable.blocked && m.kind !== 'COURSE') {
      items.push({ key: 'edit', label: 'Изменить', icon: <PencilLine className="size-4" />, onClick: () => setEditing(m) })
    }
    if (profile) items.push({ key: 'history', label: 'История изменений', icon: <History className="size-4" />, onClick: () => setHistory(m.month_number) })
    return <Menu items={items} label={`Действия: месяц №${m.month_number}`} />
  }
  const difference = Number(schedule.plan_difference ?? 0)
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="text-sm">
          {schedule.standard_course_price ? <>Стандартная {som(schedule.standard_course_price)} · </> : null}
          итоговая <b>{som(schedule.final_course_price)}</b>
          {schedule.discount_amount !== '0.00' ? <> · скидка {som(schedule.discount_amount)}</> : null}
          <span className="text-ink-secondary"> · {schedule.month_plan_mode === 'MANUAL' ? 'суммы месяцев заданы вручную'
            : schedule.month_plan_mode === 'PROPORTIONAL' ? 'скидка пропорционально цене месяцев' : 'итоговая поровну на оставшиеся месяцы'}</span>
        </p>
        <div className="flex flex-wrap gap-2">
          {profile ? <Button size="sm" variant="ghost" leftIcon={<History className="size-4" />} onClick={() => setHistory(null)}>История изменений</Button> : null}
          {canEdit && profile ? <Button size="sm" variant="secondary" onClick={() => setEditingPlan(true)}>План стоимости месяцев</Button> : null}
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5" aria-label="Общая стоимость курса">
        <Total label="Стоимость по договору" value={schedule.final_course_price} />
        <Total label="Сумма плановых месяцев" value={schedule.plan_total ?? schedule.total} />
        <Total label="Уже выставлено" value={schedule.invoiced} />
        <Total label="Будущие начисления" value={schedule.projected} />
        <Total label="Расхождение договора и плана" value={schedule.plan_difference ?? '0.00'} tone={difference ? 'danger' : 'muted'} />
      </dl>

      {schedule.course ? (
        <p className="rounded-lg border border-border bg-surface p-2 text-sm" data-testid="course-prepayment">
          Предоплата за весь курс: начисление «Весь курс» {schedule.course.number} на <b>{som(schedule.course.amount)}</b>,
          оплачено {som(schedule.course.paid)}
          {schedule.course.paid_in_full
            ? <> — <b className="text-brand-700">курс полностью оплачен</b>. Учебные месяцы закрыты этой оплатой, отдельных начислений по ним нет.</>
            : <>, остаток {som(schedule.course.balance)}. Месяцы закрываются по мере оплаты курса.</>}
        </p>
      ) : null}
      {schedule.consistent ? (
        <p className="text-sm text-ink-secondary">
          Начислено {som(schedule.invoiced)} + запланировано {som(schedule.projected)} = итоговая стоимость {som(schedule.final_course_price)}.
        </p>
      ) : (
        <p role="alert" className="flex gap-2 rounded-lg border border-danger/30 bg-danger-soft p-2 text-sm text-danger">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span><b>Ошибка расчётов.</b> {schedule.issues.join(' ')} Суммы не исправляются автоматически: проверьте месяцы через
            «Изменить» или план стоимости месяцев.</span>
        </p>
      )}
      {schedule.price_changes.length ? (
        <p className="text-xs text-ink-secondary">
          Изменения итоговой стоимости: {schedule.price_changes.map((c) => `${formatDate(c.date)}: ${c.from ? `${som(c.from)} → ` : ''}${som(c.to)}`).join('; ')}.
          Уже выставленные месяцы не пересчитываются, разница распределяется на оставшиеся.
        </p>
      ) : null}
      {canEdit && schedule.edit_blocked ? <p className="text-xs text-ink-secondary">Изменение сумм месяцев недоступно: {schedule.edit_blocked}</p> : null}

      <div className="card relative hidden overflow-x-auto xl:block">
        <table className="data-table min-w-[760px] [&_td]:px-2 [&_th]:px-2" aria-label="График оплаты">
          <thead><tr>
            <th scope="col">Месяц</th><th scope="col" className="text-right">Стандарт</th><th scope="col" className="text-right">По плану</th>
            <th scope="col" className="text-right">Начисление</th><th scope="col" className="text-right">Оплачено</th>
            <th scope="col" className="text-right">Остаток</th><th scope="col">Срок</th><th scope="col">Статус</th>
            <th scope="col" className="text-right"><span className="sr-only">Действия</span></th>
          </tr></thead>
          <tbody>
            {rows.map(({ m, v }) => (
              <tr key={key(m)} className="align-top">
                <td className="whitespace-nowrap">
                  <span className="font-medium">№{m.month_number}</span><Flags m={m} />
                  {m.number ? <span className="block text-xs text-ink-secondary">{m.number}</span> : null}
                </td>
                <td className="text-right"><Amount value={v.standard} tone="muted" /></td>
                <td className="text-right"><Amount value={v.plan} /></td>
                <td className="text-right" title={m.kind === 'COURSE' ? 'Доля стоимости курса — часть начисления «Весь курс», не отдельное начисление' : undefined}>
                  {v.charge !== null ? <Amount value={v.charge} /> : <span className="text-ink-muted">—</span>}
                  {m.kind === 'COURSE' ? <span className="block text-xs text-ink-secondary">доля курса</span> : null}
                  {m.adjusted && m.adjusted !== '0.00' ? <span className="block text-xs text-ink-secondary">корр. −{som(m.adjusted)}</span> : null}
                </td>
                <td className="text-right"><Amount value={v.paid} tone="muted" /></td>
                <td className="text-right">
                  {v.balance !== null ? <Amount value={v.balance} tone={v.status === 'overdue' ? 'danger' : undefined} /> : <span className="text-ink-muted">—</span>}
                  {m.covered_by_credit && m.covered_by_credit !== '0.00'
                    ? <span className="block text-xs text-ink-secondary" title="Прогноз: свободный аванс закроет месяц, когда он будет выставлен">аванс закроет {som(m.covered_by_credit)}</span> : null}
                </td>
                <td className="whitespace-nowrap">{due(m)}</td>
                <td className="whitespace-nowrap"><MonthStatus m={m} /></td>
                <td className="text-right">{actions(m)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="grid gap-2 md:grid-cols-2 xl:hidden" aria-label="Месяцы графика оплаты">
        {rows.map(({ m, v }) => (
          <li key={key(m)} className="card p-3 text-sm">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="font-medium">Месяц №{m.month_number}<Flags m={m} /></p>
                {m.number ? <p className="text-xs text-ink-secondary">{m.number}</p> : null}
              </div>
              <div className="flex items-center gap-2"><MonthStatus m={m} />{actions(m)}</div>
            </div>
            <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1">
              <dt className="text-ink-secondary">Стандарт</dt><dd className="text-right"><Amount value={v.standard} tone="muted" /></dd>
              <dt className="text-ink-secondary">По плану</dt><dd className="text-right"><Amount value={v.plan} /></dd>
              <dt className="text-ink-secondary">Начисление</dt><dd className="text-right">{v.charge !== null ? <Amount value={v.charge} /> : '—'}</dd>
              <dt className="text-ink-secondary">Оплачено</dt><dd className="text-right"><Amount value={v.paid} tone="muted" /></dd>
              <dt className="text-ink-secondary">Остаток</dt><dd className="text-right">{v.balance !== null ? <Amount value={v.balance} tone={v.status === 'overdue' ? 'danger' : undefined} /> : '—'}</dd>
              <dt className="text-ink-secondary">Срок</dt><dd className="text-right">{due(m)}</dd>
            </dl>
          </li>
        ))}
      </ul>

      {editingPlan && profile ? <MonthPlanModal profile={profile} schedule={schedule} onClose={() => setEditingPlan(false)} /> : null}
      {editing && profile ? <MonthEditDrawer profile={profile} month={editing} version={schedule.version} onClose={() => setEditing(null)} /> : null}
      {history !== undefined && profile ? <MonthHistoryDrawer profile={profile} month={history ?? undefined} onClose={() => setHistory(undefined)} /> : null}
    </div>
  )
}

function Total({ label, value, tone }: { label: string; value: string | null | undefined; tone?: 'danger' | 'muted' }) {
  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2">
      <dt className="text-xs text-ink-secondary">{label}</dt>
      <dd className={cn('text-sm font-semibold tabular-nums', tone === 'danger' && 'text-danger')}>{som(value)}</dd>
    </div>
  )
}

/** Цены месяцев договора и правило скидки: предпросмотр на сервере (dry_run), сохранение с причиной. */
function MonthPlanModal({ profile, schedule, onClose }: { profile: number; schedule: PaymentSchedule; onClose: () => void }) {
  const invalidate = useInvalidateFinance()
  const { run, busy } = useRunner()
  const n = schedule.months.length
  const [prices, setPrices] = useState(schedule.months.map((m) => m.standard_price ?? ''))
  const [final, setFinal] = useState(schedule.final_course_price)
  const [mode, setMode] = useState<'PROPORTIONAL' | 'MANUAL'>(schedule.month_plan_mode === 'MANUAL' ? 'MANUAL' : 'PROPORTIONAL')
  const [manual, setManual] = useState(schedule.months.map((m) => m.state === 'invoiced' ? m.amount : (m.plan_amount ?? '')))
  const [reissue, setReissue] = useState(false)
  const [reason, setReason] = useState('')
  const [preview, setPreview] = useState<MonthPlanResult | null>(null)
  const standardTotal = prices.reduce((sum, p) => sum + (Number(p.replace(',', '.')) || 0), 0)
  const body = (dry: boolean): MonthPlanBody => ({
    standard_prices: prices.map((p) => p.replace(',', '.')), final_course_price: final.replace(',', '.'), mode,
    manual_amounts: mode === 'MANUAL' ? manual.map((a) => a ? a.replace(',', '.') : null) : undefined,
    reason: reason.trim(), reissue_unstarted: reissue, dry_run: dry,
  })
  return (
    <Modal isOpen onClose={onClose} title="План стоимости учебных месяцев">
      <div className="space-y-3 text-sm">
        <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${Math.min(n, 4)}, minmax(0, 1fr))` }}>
          {prices.map((p, i) => (
            <Field key={i} label={`Месяц №${i + 1}, стандарт`} htmlFor={`mp-${i}`}>
              <Input id={`mp-${i}`} inputMode="decimal" value={p} onChange={(e) => setPrices(prices.map((x, j) => j === i ? e.target.value : x))} />
            </Field>
          ))}
        </div>
        <p className="text-ink-secondary">Стандартная стоимость: <b>{som(standardTotal.toFixed(2))}</b></p>
        <Field label="Итоговая стоимость договора" htmlFor="mp-final"><Input id="mp-final" inputMode="decimal" value={final} onChange={(e) => setFinal(e.target.value)} /></Field>
        <div role="radiogroup" aria-label="Правило распределения скидки" className="space-y-1">
          <label className="flex items-center gap-2"><input type="radio" checked={mode === 'PROPORTIONAL'} onChange={() => setMode('PROPORTIONAL')} /> Скидка пропорционально стоимости месяцев</label>
          <label className="flex items-center gap-2"><input type="radio" checked={mode === 'MANUAL'} onChange={() => setMode('MANUAL')} /> Вручную задать итоговую сумму каждого месяца</label>
        </div>
        {mode === 'MANUAL' ? (
          <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${Math.min(n, 4)}, minmax(0, 1fr))` }}>
            {manual.map((a, i) => (
              <Field key={i} label={`Месяц №${i + 1}, итог`} htmlFor={`mm-${i}`}>
                <Input id={`mm-${i}`} inputMode="decimal" value={a} disabled={schedule.months[i]?.state === 'invoiced'}
                  onChange={(e) => setManual(manual.map((x, j) => j === i ? e.target.value : x))} />
              </Field>
            ))}
          </div>
        ) : null}
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={reissue} onChange={(e) => setReissue(e.target.checked)} />
          Перевыставить выставленные, но не начатые месяцы (без уроков и корректировок) по новому плану
        </label>
        <p className="text-xs text-ink-secondary">Начатые месяцы не меняются: их суммы исправляются корректировкой начисления.</p>
        <Field label="Причина" htmlFor="mp-reason" required><Textarea id="mp-reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        {preview ? (
          <div className="rounded-lg bg-surface-muted p-2">
            <p>План: {preview.rows.map((r) => `№${r.month_number} — ${som(r.amount)}${r.issued ? ' (выставлен)' : ''}`).join(' · ')}</p>
            <p className="font-medium">Сумма плана {som(preview.total)} = итоговая {som(preview.final_course_price)} · скидка {som(preview.discount)}</p>
          </div>
        ) : null}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>Отмена</Button>
          <Button variant="secondary" isLoading={busy} onClick={() => run(async () => setPreview(await financeApi.saveMonthPlan(profile, body(true))))}>Предпросмотр</Button>
          <Button isLoading={busy} disabled={!reason.trim()} onClick={async () => {
            if (await run(() => financeApi.saveMonthPlan(profile, body(false)), 'План месяцев сохранён')) { invalidate(); onClose() }
          }}>Сохранить</Button>
        </div>
      </div>
    </Modal>
  )
}
