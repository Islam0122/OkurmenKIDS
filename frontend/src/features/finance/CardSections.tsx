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
import type { MonthPlanBody, MonthPlanResult, Payment, PaymentSchedule, Reservation } from '@/types/finance'
import { cn } from '@/utils/cn'

import { Amount, InvoiceStatusBadge, formatDate, som, useInvalidateFinance, useRunner } from './ui'

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
                  <span className="block max-w-48 truncate text-xs text-ink-secondary" title={paidFor(p)}>{paidFor(p)}</span>
                </td>
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

function due(m: PaymentSchedule['months'][number]): string {
  if (m.state !== 'invoiced') return '—'
  if (m.due_lesson) return `${m.due_lesson}-й урок (сейчас ${m.lessons_used ?? 0})`
  return formatDate(m.due_date ?? null)
}

/** График оплаты: цена месяца по плану договора, начисление, оплачено, остаток,
 * срок и статус; прогноз оставшихся месяцев (как их выставит backend) и проверка суммы. */
export function ScheduleBlock({ schedule, profile, canEdit }: { schedule: PaymentSchedule; profile?: number; canEdit?: boolean }) {
  const [editing, setEditing] = useState(false)
  const hasPlan = schedule.months.some((m) => m.standard_price !== null)
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm">
          {schedule.standard_course_price ? <>Стандартная {som(schedule.standard_course_price)} · </> : null}
          итоговая <b>{som(schedule.final_course_price)}</b>
          {schedule.discount_amount !== '0.00' ? <> · скидка {som(schedule.discount_amount)}</> : null}
          <span className="text-ink-secondary"> · {schedule.month_plan_mode === 'MANUAL' ? 'суммы месяцев заданы вручную'
            : schedule.month_plan_mode === 'PROPORTIONAL' ? 'скидка пропорционально цене месяцев' : 'итоговая поровну на оставшиеся месяцы'}</span>
        </p>
        {canEdit && profile ? <Button size="sm" variant="secondary" onClick={() => setEditing(true)}>План стоимости месяцев</Button> : null}
      </div>
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
        <table className="data-table min-w-[820px]" aria-label="График оплаты">
          <thead><tr>
            <th>Месяц</th>{hasPlan ? <><th>Стандарт</th><th>По плану</th></> : null}<th>Начисление</th><th>Оплачено</th>
            <th title="Прогноз: свободный аванс закроет месяц, когда он будет выставлен">Закроет аванс (прогноз)</th><th>Остаток</th><th>Срок</th><th>Статус</th>
          </tr></thead>
          <tbody>
            {schedule.months.map((m) => (
              <tr key={`${m.month_number}-${m.invoice ?? 'p'}`}>
                <td className="whitespace-nowrap">№{m.month_number}{m.number ? <span className="text-ink-secondary"> · {m.number}</span> : null}</td>
                {hasPlan ? <><td><Amount value={m.standard_price} tone="muted" /></td><td><Amount value={m.plan_amount} /></td></> : null}
                <td><Amount value={m.amount} /></td>
                <td><Amount value={m.paid} tone="muted" /></td>
                <td><Amount value={m.covered_by_credit} tone="muted" /></td>
                <td><Amount value={m.state === 'invoiced' ? m.balance : m.to_pay} /></td>
                <td className="whitespace-nowrap">{due(m)}</td>
                <td>{m.state === 'invoiced' && m.status ? <InvoiceStatusBadge status={m.status} label={m.status_display ?? ''} /> : STATE[m.state]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editing && profile ? <MonthPlanModal profile={profile} schedule={schedule} onClose={() => setEditing(false)} /> : null}
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
