import { useState } from 'react'
import { Printer } from 'lucide-react'
import { Link } from 'react-router-dom'

import { financeApi } from '@/api/finance'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Textarea } from '@/components/ui/Textarea'
import { Field } from '@/features/worklog/formUi'
import type { Payment, PaymentSchedule, Reservation } from '@/types/finance'
import { cn } from '@/utils/cn'

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
  const active = p.allocations.filter((a) => a.status === 'ACTIVE')
  if (active.length) return `на ${active.map((a) => a.invoice_number).join(', ')}`
  return p.kind === 'payment' && p.status === 'confirmed' ? 'аванс' : ''
}

/** «Платежи и чеки»: одна операция — одна строка (на телефоне — карточка).
 * Бронь — не отдельная строка, а тип операции её платежа. */
export function OperationsTable({ payments, canPay, onReverse }: {
  payments: Payment[]
  canPay: boolean
  onReverse: (p: Payment) => void
}) {
  const actions = (p: Payment) => (
    <div className="flex flex-nowrap justify-end gap-1 whitespace-nowrap">
      <Link to={`/finance/payments/${p.id}`} className="inline-flex h-8 items-center rounded-lg px-2 text-sm text-brand-700 hover:bg-brand-50">
        Открыть
      </Link>
      {canPay && p.status === 'confirmed' ? <Button size="sm" variant="ghost" onClick={() => onReverse(p)}>Сторно</Button> : null}
    </div>
  )
  const receipt = (p: Payment) => p.receipt ? (
    <Link to={`/finance/receipts/${p.receipt.id}`} className="inline-flex items-center gap-1 whitespace-nowrap text-sm text-brand-700 hover:underline">
      <Printer className="size-4" aria-hidden />{p.receipt.number}
    </Link>
  ) : '—'
  return (
    <>
      <div className="card hidden overflow-x-auto md:block">
        <table className="data-table min-w-[760px]" aria-label="Платежи и чеки">
          <thead>
            <tr>
              {['Дата', 'Тип операции', 'Сумма', 'Способ оплаты', 'Статус', 'Кто принял', 'Номер чека', 'Действия'].map((h) => (
                <th key={h} scope="col" className={cn('whitespace-nowrap', h === 'Действия' && 'text-right')}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {payments.map((p) => (
              <tr key={p.id} className="align-top">
                <td className="whitespace-nowrap">{formatDate(p.received_date)}</td>
                <td>
                  <span className="whitespace-nowrap font-medium">{operationType(p)}</span>
                  <span className="block max-w-40 truncate text-xs text-ink-secondary" title={paidFor(p)}>{paidFor(p)}</span>
                </td>
                <td className="whitespace-nowrap"><Amount value={p.kind === 'refund' ? `-${p.amount}` : p.amount} /></td>
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
      <ul className="space-y-2 md:hidden" aria-label="Платежи и чеки">
        {payments.map((p) => (
          <li key={p.id} className="card p-3 text-sm">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="font-medium">{operationType(p)} · {formatDate(p.received_date)}</p>
                <p className="text-xs text-ink-secondary">{paidFor(p)}</p>
              </div>
              <Amount value={p.kind === 'refund' ? `-${p.amount}` : p.amount} />
            </div>
            <dl className="mt-2 grid grid-cols-2 gap-1 text-xs">
              <dt className="text-ink-secondary">Способ</dt><dd>{p.method_display}</dd>
              <dt className="text-ink-secondary">Статус</dt><dd><StatusBadge p={p} /></dd>
              <dt className="text-ink-secondary">Принял</dt><dd>{p.created_by_name ?? '—'}</dd>
              <dt className="text-ink-secondary">Чек</dt><dd>{receipt(p)}</dd>
            </dl>
            <div className="mt-2">{actions(p)}</div>
          </li>
        ))}
      </ul>
    </>
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
          ? 'Бронь оплачена: деньги платежа останутся авансом договора (возврат — отдельной операцией). Если деньги не поступали — аннулируйте платёж брони на странице платежа.'
          : 'Неоплаченная бронь будет отменена.'}
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

const STATE: Record<string, string> = { invoiced: 'выставлен', planned: 'оплачен по договору', future: 'будет выставлен' }

/** График оплаты: выставленные месяцы и прогноз оставшихся (как их выставит backend), покрытие авансом и проверка суммы. */
export function ScheduleBlock({ schedule }: { schedule: PaymentSchedule }) {
  return (
    <div className="space-y-2">
      {schedule.consistent ? (
        <p className="text-sm text-ink-secondary">
          Начислено {som(schedule.invoiced)} + запланировано {som(schedule.projected)} = итоговая стоимость {som(schedule.final_course_price)}.
        </p>
      ) : (
        <p className="rounded-lg bg-danger-soft p-2 text-sm text-danger">Несоответствие: {schedule.issues.join(' ')} Обратитесь к администратору оплаты — данные не исправляются автоматически.</p>
      )}
      {schedule.price_changes.length ? (
        <p className="text-xs text-ink-secondary">
          Изменения итоговой стоимости: {schedule.price_changes.map((c) => `${formatDate(c.date)}: ${c.from ? `${som(c.from)} → ` : ''}${som(c.to)}`).join('; ')}.
          Уже выставленные месяцы не пересчитываются, разница распределяется на оставшиеся.
        </p>
      ) : null}
      <div className="card overflow-x-auto">
        <table className="data-table min-w-[560px]" aria-label="График оплаты">
          <thead><tr><th>Месяц</th><th>Состояние</th><th>Сумма</th><th>Оплачено</th><th>Закроет аванс</th><th>Осталось оплатить</th></tr></thead>
          <tbody>
            {schedule.months.map((m) => (
              <tr key={`${m.month_number}-${m.invoice ?? 'p'}`}>
                <td className="whitespace-nowrap">№{m.month_number}{m.number ? <span className="block text-xs text-ink-secondary">{m.number}</span> : null}</td>
                <td>{STATE[m.state]}</td>
                <td><Amount value={m.amount} /></td>
                <td><Amount value={m.paid} tone="muted" /></td>
                <td><Amount value={m.covered_by_credit} tone="muted" /></td>
                <td><Amount value={m.state === 'invoiced' ? m.balance : m.to_pay} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
