import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AxiosError } from 'axios'
import { CalendarClock, History, Pencil, Printer, ReceiptText, XCircle } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'

import { financeApi } from '@/api/finance'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { BackLink } from '@/components/ui/BackLink'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { DataTable } from '@/components/ui/DataTable'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { Field } from '@/features/worklog/formUi'
import type { AuditEntry, Payment, PaymentCorrection } from '@/types/finance'

import { periodMonth } from './period'
import { Amount, FINANCE_KEY, Loadable, formatDate, formatDateTime, som, today, useFinanceMe, useFinanceOptions,
  useInvalidateFinance, useRunner } from './ui'

const ACTIONS: Record<string, string> = {
  billing_payment: 'Платёж зарегистрирован',
  billing_payment_correct: 'Исправление платежа',
  billing_payment_created_at: 'Исправление даты создания',
  billing_payment_reverse: 'Аннулирование платежа',
  billing_allocate: 'Распределение на начисление',
  billing_allocation_reverse: 'Сторно распределения',
  billing_receipt_issue: 'Чек выдан',
  billing_receipt_update: 'Чек обновлён (номер прежний)',
  billing_receipt_reissue: 'Чек перевыпущен',
  billing_receipt_cancel: 'Чек аннулирован',
  billing_receipt_print: 'Печать чека',
  billing_refund: 'Возврат',
}

type Dialog = 'edit' | 'date' | 'void' | null

/** Платёж: данные, распределения, чек, история и действия бухгалтера.
 * Все изменения — через backend (`payments/{id}/correct|reverse|created-at`),
 * где проверяются права и пишется журнал; директор видит только просмотр. */
export function PaymentDetailPage() {
  const id = Number(useParams().paymentId)
  const me = useFinanceMe()
  const [dialog, setDialog] = useState<Dialog>(null)
  const payment = useQuery({ queryKey: [...FINANCE_KEY, 'payment', id], queryFn: () => financeApi.payment(id) })
  const history = useQuery({ queryKey: [...FINANCE_KEY, 'payment-history', id], queryFn: () => financeApi.paymentHistory(id) })
  const canEdit = me.data?.can_record_payments ?? false
  return (
    <div>
      <BackLink to="/finance/payments">Все платежи</BackLink>
      <Loadable query={payment}>
        {(p) => {
          const live = p.status === 'confirmed'
          return (
            <>
              <PageHeader title={`Платёж №${p.id}`}
                badge={live ? <Badge tone="success">Проведён</Badge> : <Badge tone="muted">Аннулирован</Badge>}
                description={`${p.student_name} · ${p.group_name} · ${p.program_name}`}
                actions={
                  <div className="flex flex-wrap gap-2">
                    {canEdit && live ? (
                      <>
                        <Button leftIcon={<Pencil className="size-4" />} onClick={() => setDialog('edit')}>Редактировать</Button>
                        <Button variant="secondary" leftIcon={<CalendarClock className="size-4" />} onClick={() => setDialog('date')}>Исправить дату</Button>
                        <Button variant="danger" leftIcon={<XCircle className="size-4" />} onClick={() => setDialog('void')}>Аннулировать</Button>
                      </>
                    ) : null}
                  </div>
                } />
              <div className="grid gap-4 lg:grid-cols-2">
                <Card title="Операция">
                  <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                    <dt className="text-ink-secondary">Сумма</dt><dd className="font-semibold">{som(p.kind === 'refund' ? `-${p.amount}` : p.amount)}</dd>
                    <dt className="text-ink-secondary">Деньги получены</dt><dd>{formatDate(p.received_date)} ({periodMonth(p.received_date)})</dd>
                    <dt className="text-ink-secondary">Запись создана</dt><dd>{formatDateTime(p.created_at)} · {p.created_by_name ?? '—'}</dd>
                    <dt className="text-ink-secondary">Назначение</dt><dd>{p.kind === 'refund' ? 'Возврат' : p.purpose_display || 'Оплата обучения'}</dd>
                    <dt className="text-ink-secondary">Способ</dt><dd>{p.method_display}</dd>
                    <dt className="text-ink-secondary">Документ</dt><dd>{p.reference || '—'}</dd>
                    <dt className="text-ink-secondary">Не распределено (аванс)</dt><dd>{som(p.unallocated)}</dd>
                    <dt className="text-ink-secondary">Комментарий</dt><dd>{p.comment || '—'}</dd>
                    {p.void_reason ? <><dt className="text-ink-secondary">Причина аннулирования</dt><dd>{p.void_reason}</dd></> : null}
                  </dl>
                  <Link to={`/finance/students/${p.billing_profile}`} className="mt-3 inline-block text-sm text-brand-700 hover:underline">Карточка студента</Link>
                </Card>
                <Card title="Чек" description="Внутренний чек Okurmen Kids, не фискальный документ.">
                  {p.receipt ? (
                    <div className="space-y-3 text-sm">
                      <p>№ <b>{p.receipt.number}</b> · {p.receipt.status === 'ISSUED' ? 'выдан' : 'аннулирован'}</p>
                      <div className="flex flex-wrap gap-2">
                        <Link to={`/finance/receipts/${p.receipt.id}`}>
                          <Button size="sm" variant="secondary" leftIcon={<ReceiptText className="size-4" />}>Просмотреть чек</Button>
                        </Link>
                        <Link to={`/finance/receipts/${p.receipt.id}?print=1`}>
                          <Button size="sm" variant="secondary" leftIcon={<Printer className="size-4" />}>Повторно распечатать</Button>
                        </Link>
                      </div>
                      <p className="text-xs text-ink-secondary">Повторная печать не создаёт ни платежа, ни нового чека.</p>
                    </div>
                  ) : <p className="text-sm text-ink-secondary">Чека нет.</p>}
                </Card>
              </div>
              <Card className="mt-4" title="Распределение на начисления" padding="none">
                <DataTable rows={p.allocations} getRowKey={(a) => a.id} columns={[
                  { key: 'n', header: 'Начисление', render: (a) => a.invoice_number },
                  { key: 'p', header: 'Период начисления', render: (a) => periodMonth(a.invoice_period_date) },
                  { key: 'a', header: 'Сумма', render: (a) => <Amount value={a.amount} /> },
                  { key: 's', header: 'Статус', render: (a) => a.status === 'ACTIVE' ? 'Действует' : `Сторно: ${a.reverse_reason ?? ''}` },
                ]} />
                {p.allocations.length === 0 ? <p className="card-body text-sm text-ink-secondary">Не распределён — аванс.</p> : null}
              </Card>
              <Card className="mt-4" title="История изменений" actions={<History className="size-4 text-ink-secondary" />} padding="none">
                <Loadable query={history} empty={(d) => d.length === 0} emptyTitle="Записей нет">
                  {(rows) => <HistoryTable rows={rows} />}
                </Loadable>
              </Card>
              {dialog === 'edit' ? <EditDialog payment={p} onClose={() => setDialog(null)} /> : null}
              {dialog === 'date' ? <EditDialog payment={p} dateOnly onClose={() => setDialog(null)} /> : null}
              {dialog === 'void' ? <VoidDialog payment={p} onClose={() => setDialog(null)} /> : null}
            </>
          )
        }}
      </Loadable>
    </div>
  )
}

function HistoryTable({ rows }: { rows: AuditEntry[] }) {
  return (
    <DataTable rows={rows} getRowKey={(r) => r.id} columns={[
      { key: 'd', header: 'Когда', render: (r) => formatDateTime(r.created_at) },
      { key: 'u', header: 'Кто', render: (r) => r.actor },
      { key: 'a', header: 'Действие', render: (r) => ACTIONS[r.action] ?? r.action },
      { key: 'c', header: 'Было → стало', render: (r) => <Diff entry={r} /> },
      { key: 'r', header: 'Причина', render: (r) => r.reason || '—' },
    ]} />
  )
}

const LABELS: Record<string, string> = {
  received_date: 'дата поступления', amount: 'сумма', method: 'способ', reference: 'документ', comment: 'комментарий',
  purpose: 'назначение', billing_profile_id: 'договор', created_at: 'дата создания', status: 'статус', number: 'номер чека',
}

function Diff({ entry }: { entry: AuditEntry }) {
  const keys = Object.keys(LABELS).filter((k) => k in entry.old_values && JSON.stringify(entry.old_values[k]) !== JSON.stringify(entry.new_values[k]))
  if (!keys.length) return <span className="text-ink-secondary">—</span>
  return (
    <ul className="text-xs">
      {keys.map((k) => <li key={k}>{LABELS[k]}: {String(entry.old_values[k] ?? '—')} → <b>{String(entry.new_values[k] ?? '—')}</b></li>)}
    </ul>
  )
}

function errorOf(error: unknown): { code?: string; detail?: string } {
  return error instanceof AxiosError ? (error.response?.data ?? {}) : {}
}

/** Исправление: только изменённые поля уходят на backend. `dateOnly` — быстрая форма даты. */
function EditDialog({ payment, dateOnly, onClose }: { payment: Payment; dateOnly?: boolean; onClose: () => void }) {
  const options = useFinanceOptions()
  const invalidate = useInvalidateFinance()
  const { run, busy } = useRunner()
  const card = useQuery({ queryKey: [...FINANCE_KEY, 'card', payment.billing_profile], queryFn: () => financeApi.card(payment.billing_profile),
    enabled: !dateOnly })
  const active = payment.allocations.filter((a) => a.status === 'ACTIVE')
  const [date, setDate] = useState(payment.received_date)
  const [amount, setAmount] = useState(payment.amount)
  const [method, setMethod] = useState(payment.method)
  const [reference, setReference] = useState(payment.reference)
  const [comment, setComment] = useState(payment.comment)
  const [purpose, setPurpose] = useState(payment.purpose)
  const [realloc, setRealloc] = useState(false)
  const [rows, setRows] = useState(active.map((a) => ({ invoice: String(a.invoice), amount: a.amount })))
  const [reason, setReason] = useState('')
  const [closedWarning, setClosedWarning] = useState<string | null>(null)
  const [confirmClosed, setConfirmClosed] = useState(false)

  function body(): PaymentCorrection {
    const b: PaymentCorrection = { reason: reason.trim(), confirm_closed_period: confirmClosed }
    if (date !== payment.received_date) b.received_date = date
    if (dateOnly) return b
    if (amount !== payment.amount) b.amount = amount.replace(',', '.')
    if (method !== payment.method) b.method = method
    if (reference !== payment.reference) b.reference = reference
    if (comment !== payment.comment) b.comment = comment
    if (purpose !== payment.purpose && (purpose === 'tuition' || purpose === 'prepayment')) b.purpose = purpose
    if (realloc) b.allocations = rows.filter((r) => r.invoice && r.amount).map((r) => ({ invoice: Number(r.invoice), amount: r.amount.replace(',', '.') }))
    return b
  }

  async function save() {
    const ok = await run(async () => {
      try {
        await financeApi.correctPayment(payment.id, body())
      } catch (error) {
        const e = errorOf(error)
        if (e.code === 'closed_period') setClosedWarning(e.detail ?? '')
        throw error
      }
    })
    if (ok) {
      invalidate()
      onClose()
    }
  }

  const monthChanges = date !== payment.received_date && date.slice(0, 7) !== payment.received_date.slice(0, 7)
  const invoices = (card.data?.invoices ?? []).map((i) => ({ value: String(i.id),
    label: `${i.number} · ${periodMonth(i.period_date)} · ${som(i.amount)}` }))
  return (
    <Modal isOpen onClose={onClose} title={dateOnly ? 'Исправить дату поступления' : `Редактировать платёж №${payment.id}`}>
      <div className="space-y-3">
        <Field label="Дата фактического поступления денег" htmlFor="pc-date">
          <Input id="pc-date" type="date" max={today()} value={date} onChange={(e) => setDate(e.target.value)} />
        </Field>
        {monthChanges ? (
          <p className="rounded-lg bg-warning-soft p-2 text-sm text-warning">
            Поступление переедет из «{periodMonth(payment.received_date)}» в «{periodMonth(date)}» — изменятся отчёты обоих месяцев.
            Период начисления не меняется, номер чека сохраняется.
          </p>
        ) : null}
        {!dateOnly ? (
          <>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Сумма, сом" htmlFor="pc-amount"><Input id="pc-amount" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
              <Field label="Способ оплаты" htmlFor="pc-method">
                <Select id="pc-method" value={method} onChange={(e) => setMethod(e.target.value)} options={options.data?.payment_methods ?? []} />
              </Field>
              <Field label="Назначение" htmlFor="pc-purpose">
                <Select id="pc-purpose" value={purpose} onChange={(e) => setPurpose(e.target.value)}
                  options={[{ value: 'tuition', label: 'Оплата обучения' }, { value: 'prepayment', label: 'Предоплата / аванс' }]} />
              </Field>
              <Field label="Номер документа" htmlFor="pc-ref"><Input id="pc-ref" value={reference} onChange={(e) => setReference(e.target.value)} /></Field>
            </div>
            <Field label="Комментарий" htmlFor="pc-comment"><Textarea id="pc-comment" rows={2} value={comment} onChange={(e) => setComment(e.target.value)} /></Field>
            {amount !== payment.amount ? <p className="text-xs text-ink-secondary">Изменение суммы перевыпускает чек (прежний номер и данные сохраняются в истории).</p> : null}
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={realloc} onChange={(e) => setRealloc(e.target.checked)} /> Изменить распределение между начислениями
            </label>
            {realloc ? (
              <div className="space-y-2">
                {rows.map((r, i) => (
                  <div key={i} className="grid grid-cols-[1fr_140px_auto] gap-2">
                    <Select aria-label="Начисление" value={r.invoice} placeholder="Начисление" options={invoices}
                      onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, invoice: e.target.value } : x))} />
                    <Input aria-label="Сумма распределения" value={r.amount} onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, amount: e.target.value } : x))} />
                    <Button size="sm" variant="ghost" onClick={() => setRows(rows.filter((_, j) => j !== i))}>Убрать</Button>
                  </div>
                ))}
                <Button size="sm" variant="secondary" onClick={() => setRows([...rows, { invoice: '', amount: '' }])}>Добавить строку</Button>
                <p className="text-xs text-ink-secondary">Нераспределённый остаток останется авансом договора.</p>
              </div>
            ) : null}
          </>
        ) : null}
        <Field label="Причина корректировки" htmlFor="pc-reason" required>
          <Textarea id="pc-reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        {closedWarning ? (
          <label className="flex items-start gap-2 rounded-lg bg-warning-soft p-2 text-sm text-warning">
            <input type="checkbox" className="mt-1" checked={confirmClosed} onChange={(e) => setConfirmClosed(e.target.checked)} />
            <span>{closedWarning} Отметьте, чтобы подтвердить исправление — оно будет сохранено в журнале.</span>
          </label>
        ) : null}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>Отмена</Button>
          <Button isLoading={busy} disabled={busy || !reason.trim()} onClick={save}>Сохранить</Button>
        </div>
      </div>
    </Modal>
  )
}

function VoidDialog({ payment, onClose }: { payment: Payment; onClose: () => void }) {
  const invalidate = useInvalidateFinance()
  const { run, busy } = useRunner()
  const [reason, setReason] = useState('')
  return (
    <Modal isOpen onClose={onClose} title="Аннулировать платёж">
      <dl className="grid grid-cols-2 gap-1 rounded-lg bg-danger-soft p-3 text-sm">
        <dt>Платёж</dt><dd className="font-semibold">№{payment.id}{payment.receipt ? ` · чек ${payment.receipt.number}` : ''}</dd>
        <dt>Студент</dt><dd>{payment.student_name}</dd>
        <dt>Сумма</dt><dd>{som(payment.amount)}</dd>
        <dt>Дата поступления</dt><dd>{formatDate(payment.received_date)}</dd>
      </dl>
      <p className="mt-3 text-sm text-ink-secondary">
        Распределения будут сторнированы — начисления снова станут долгом, чек будет аннулирован. Записи не удаляются,
        договор и другие платежи не меняются. Повторно аннулировать нельзя.
      </p>
      <Field label="Причина" htmlFor="pv-reason" required className="mt-3">
        <Textarea id="pv-reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Отмена</Button>
        <Button variant="danger" isLoading={busy} disabled={busy || !reason.trim()} onClick={async () => {
          if (await run(() => financeApi.reversePayment(payment.id, reason.trim()), 'Платёж аннулирован')) {
            invalidate()
            onClose()
          }
        }}>Аннулировать</Button>
      </div>
    </Modal>
  )
}
