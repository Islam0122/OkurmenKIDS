import { Fragment, useState } from 'react'
import { Calculator, CheckCircle2, FileDown, FileSpreadsheet, Plus, RotateCcw, Undo2, Wallet, XCircle } from 'lucide-react'
import { useParams } from 'react-router-dom'

import { accountingApi, newIdempotencyKey } from '@/api/accounting'
import { PageHeader } from '@/components/layout/PageHeader'
import { BackLink } from '@/components/ui/BackLink'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { ErrorState } from '@/components/ui/ErrorState'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { StatCard } from '@/components/ui/StatCard'
import { StatGrid } from '@/components/ui/StatGrid'
import { Textarea } from '@/components/ui/Textarea'
import { useAccountingMutation, useAccountingOptions, usePayroll } from '@/hooks/useAccounting'
import { Field } from '@/features/worklog/formUi'
import type { AuditEntry, PayrollDetail, PayrollLine } from '@/types/accounting'

import {
  Notice,
  PayrollStatusBadge,
  ReasonModal,
  Section,
  formatDate,
  formatDateTime,
  som,
  today,
  useRunner,
} from './shared'

const ACTION_LABEL: Record<string, string> = {
  calculate: 'Расчёт',
  recalculate: 'Пересчёт',
  approve: 'Утверждение',
  reject: 'Отклонение',
  return: 'Возврат на исправление',
  reopen: 'Переоткрытие',
  void: 'Отмена',
  create: 'Создание',
}

const ENTITY_LABEL: Record<string, string> = {
  payroll: 'Начисление',
  payrollpayment: 'Выплата',
  payrolladjustment: 'Корректировка',
}

type Prompt = null | 'return' | 'reopen' | 'void' | { payment: number } | { adjustment: number; mode: 'void' | 'reject' }

export function PayrollDetailPage() {
  const id = Number(useParams().id)
  const payroll = usePayroll(id)
  const options = useAccountingOptions()
  const { run, busy } = useRunner()
  const mutate = useAccountingMutation(async (fn: () => Promise<unknown>) => fn())
  const [prompt, setPrompt] = useState<Prompt>(null)
  const [paying, setPaying] = useState(false)
  const [adjusting, setAdjusting] = useState(false)

  if (payroll.isLoading) return <LoadingState />
  if (payroll.isError || !payroll.data) return <ErrorState onRetry={() => payroll.refetch()} />
  const p = payroll.data
  const caps = options.data
  const editable = ['DRAFT', 'CALCULATED', 'RETURNED'].includes(p.status)
  const locked = ['APPROVED', 'PARTIALLY_PAID', 'PAID'].includes(p.status)
  const act = (fn: () => Promise<unknown>, message: string) => run(() => mutate.mutateAsync(fn), message)

  return (
    <div>
      <BackLink to="/accounting">К начислениям</BackLink>
      <PageHeader
        title={p.employee_name}
        description={`${p.position || '—'} · ${p.salary_type_display || '—'} · период ${p.period_label}`}
        badge={<PayrollStatusBadge status={p.status} label={p.status_display} />}
      />

      <div className="mb-4 flex flex-wrap gap-2">
        {caps?.can_operate && editable ? (
          <Button leftIcon={<Calculator className="size-4" />} isLoading={busy}
            onClick={() => act(() => accountingApi.recalculate(p.id), 'Пересчитано')}>
            {p.calculated_at ? 'Пересчитать' : 'Рассчитать'}
          </Button>
        ) : null}
        {caps?.can_approve && p.status === 'CALCULATED' ? (
          <>
            <Button leftIcon={<CheckCircle2 className="size-4" />} isLoading={busy} disabled={p.has_errors}
              onClick={() => act(() => accountingApi.approve(p.id), 'Начисление утверждено')}>
              Подтвердить начисление
            </Button>
            <Button variant="secondary" leftIcon={<Undo2 className="size-4" />} onClick={() => setPrompt('return')}>
              Вернуть на исправление
            </Button>
          </>
        ) : null}
        {caps?.can_approve && p.status === 'APPROVED' ? (
          <Button variant="ghost" leftIcon={<RotateCcw className="size-4" />} onClick={() => setPrompt('reopen')}>
            Переоткрыть
          </Button>
        ) : null}
        {caps?.can_operate && locked && Number(p.amount_due) > 0 ? (
          <Button leftIcon={<Wallet className="size-4" />} onClick={() => setPaying(true)}>Зарегистрировать выплату</Button>
        ) : null}
        {caps?.can_operate && p.status !== 'VOID' ? (
          <Button variant="secondary" leftIcon={<Plus className="size-4" />} onClick={() => setAdjusting(true)}>
            Добавить корректировку
          </Button>
        ) : null}
        <Button variant="ghost" leftIcon={<FileDown className="size-4" />} onClick={() => run(() => accountingApi.downloadPayrollPdf(p.id))}>
          Скачать PDF
        </Button>
        <Button variant="ghost" leftIcon={<FileSpreadsheet className="size-4" />} onClick={() => run(() => accountingApi.downloadPayrollXlsx(p.id))}>
          Экспорт Excel
        </Button>
        {caps?.can_operate && editable ? (
          <Button variant="ghost" leftIcon={<XCircle className="size-4" />} onClick={() => setPrompt('void')}>Аннулировать</Button>
        ) : null}
      </div>

      {p.return_reason && p.status === 'RETURNED' ? <Notice tone="warning" items={[`Возвращено директором: ${p.return_reason}`]} /> : null}
      <div className="space-y-2">
        <Notice tone="danger" items={p.errors} />
        <Notice tone="warning" items={p.warnings} />
      </div>

      <div className="mt-4">
        <StatGrid>
          <StatCard label="Начислено" value={som(p.total_accrued)} />
          <StatCard label="Корректировки" value={som(p.total_adjustments)} />
          <StatCard label="Выплачено" value={som(p.total_paid)} />
          <StatCard label="Остаток к выплате" value={som(p.amount_due)} tone={Number(p.amount_due) > 0 ? 'warning' : 'default'} />
        </StatGrid>
      </div>
      {p.active_students !== null ? (
        <p className="mt-3 text-sm text-ink-secondary">Активных студентов в периоде: <b>{p.active_students}</b></p>
      ) : null}

      <Section title="Детализация начисления">
        <Lines lines={p.lines} />
      </Section>

      {p.rules.length ? (
        <Section title="Использованные зарплатные правила">
          <ul className="space-y-1 text-sm text-ink-secondary">
            {p.rules.map((r) => (
              <li key={r.id}>
                #{r.id} · {r.rule_type_display}
                {r.percentage !== null ? ` ${Number(r.percentage)}%` : r.amount !== null ? ` ${som(r.amount)}` : ''}
                {r.group_name ? ` · группа ${r.group_name}` : r.program_name ? ` · программа ${r.program_name}` : ''}
                {` · ${r.calculation_method_display}`} · с {formatDate(r.effective_from)}
                {r.effective_to ? ` по ${formatDate(r.effective_to)}` : ''}
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      <Section title="Корректировки">
        {p.adjustments.length === 0 ? <p className="text-sm text-ink-muted">Корректировок нет.</p> : (
          <div className="card overflow-x-auto">
            <table className="data-table">
              <thead><tr><th>Тип</th><th>Причина</th><th className="text-right">Сумма</th><th>Статус</th><th>Кто</th><th /></tr></thead>
              <tbody>
                {p.adjustments.map((a) => (
                  <tr key={a.id}>
                    <td>{a.kind_display}</td>
                    <td className="text-sm">{a.reason}</td>
                    <td className="text-right">{som(a.amount)}</td>
                    <td><Badge tone={a.status === 'APPLIED' ? 'success' : a.status === 'PENDING' ? 'warning' : 'muted'}>{a.status_display}</Badge></td>
                    <td className="text-xs">{a.created_by_name}{a.decided_by_name ? ` → ${a.decided_by_name}` : ''}</td>
                    <td className="whitespace-nowrap text-right">
                      {a.status === 'PENDING' && caps?.can_approve ? (
                        <>
                          <Button size="sm" onClick={() => act(() => accountingApi.decideAdjustment(a.id, true), 'Корректировка применена')}>Утвердить</Button>{' '}
                          <Button size="sm" variant="ghost" onClick={() => setPrompt({ adjustment: a.id, mode: 'reject' })}>Отклонить</Button>
                        </>
                      ) : null}
                      {caps?.can_operate && (a.status === 'PENDING' || (a.status === 'APPLIED' && editable)) ? (
                        <Button size="sm" variant="ghost" onClick={() => setPrompt({ adjustment: a.id, mode: 'void' })}>Отменить</Button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section title="История выплат">
        {p.payments.length === 0 ? <p className="text-sm text-ink-muted">Выплат ещё не было.</p> : (
          <div className="card overflow-x-auto">
            <table className="data-table">
              <thead><tr><th>Дата</th><th>Способ</th><th>Документ</th><th className="text-right">Сумма</th><th>Статус</th><th /></tr></thead>
              <tbody>
                {p.payments.map((pay) => (
                  <tr key={pay.id} className={pay.status === 'VOID' ? 'opacity-60' : undefined}>
                    <td>{formatDate(pay.payment_date)}{pay.is_advance ? <Badge className="ml-2" tone="info">аванс</Badge> : null}</td>
                    <td>{pay.payment_method_display}</td>
                    <td className="text-sm">{pay.reference || '—'}{pay.comment ? <p className="text-xs text-ink-muted">{pay.comment}</p> : null}</td>
                    <td className="text-right">{som(pay.amount)}</td>
                    <td>
                      <Badge tone={pay.status === 'VOID' ? 'muted' : 'success'}>{pay.status_display}</Badge>
                      {pay.void_reason ? <p className="text-xs text-ink-muted">{pay.void_reason}</p> : null}
                    </td>
                    <td className="text-right">
                      {caps?.can_operate && pay.status === 'CONFIRMED' ? (
                        <Button size="sm" variant="ghost" onClick={() => setPrompt({ payment: pay.id })}>Отменить</Button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section title="История изменений">
        <AuditList entries={p.audit ?? []} />
      </Section>

      <PaymentModal payroll={p} isOpen={paying} onClose={() => setPaying(false)} methods={caps?.payment_methods ?? []}
        onSubmit={(body, key) => act(() => accountingApi.registerPayment(p.id, body, key), 'Выплата зарегистрирована')} />
      <AdjustmentModal isOpen={adjusting} onClose={() => setAdjusting(false)} locked={locked}
        kinds={caps?.adjustment_kinds ?? []}
        onSubmit={(body) => act(() => accountingApi.addAdjustment(p.id, body), locked ? 'Корректировка отправлена на утверждение' : 'Корректировка добавлена')} />

      <ReasonModal isOpen={prompt === 'return'} title="Вернуть на исправление" confirmLabel="Вернуть" onClose={() => setPrompt(null)}
        onConfirm={(reason) => act(() => accountingApi.returnForFix(p.id, reason), 'Начисление возвращено')} />
      <ReasonModal isOpen={prompt === 'reopen'} title="Переоткрыть начисление" confirmLabel="Переоткрыть"
        description="Начисление снова станет рассчитанным; прежние итоги остаются в журнале изменений." onClose={() => setPrompt(null)}
        onConfirm={(reason) => act(() => accountingApi.reopen(p.id, reason), 'Начисление переоткрыто')} />
      <ReasonModal isOpen={prompt === 'void'} title="Аннулировать начисление" tone="danger" confirmLabel="Аннулировать" onClose={() => setPrompt(null)}
        onConfirm={(reason) => act(() => accountingApi.voidPayroll(p.id, reason), 'Начисление аннулировано')} />
      <ReasonModal isOpen={typeof prompt === 'object' && prompt !== null && 'payment' in prompt} title="Отменить выплату" tone="danger"
        confirmLabel="Отменить выплату" description="Выплата не удаляется: она остаётся в истории со статусом «Отменена»." onClose={() => setPrompt(null)}
        onConfirm={(reason) => act(() => accountingApi.voidPayment((prompt as { payment: number }).payment, reason), 'Выплата отменена')} />
      <ReasonModal isOpen={typeof prompt === 'object' && prompt !== null && 'adjustment' in prompt}
        title={typeof prompt === 'object' && prompt !== null && 'mode' in prompt && prompt.mode === 'reject' ? 'Отклонить корректировку' : 'Отменить корректировку'}
        tone="danger" confirmLabel="Подтвердить" onClose={() => setPrompt(null)}
        onConfirm={(reason) => {
          const target = prompt as { adjustment: number; mode: 'void' | 'reject' }
          return act(
            () => (target.mode === 'reject'
              ? accountingApi.decideAdjustment(target.adjustment, false, reason)
              : accountingApi.voidAdjustment(target.adjustment, reason)),
            'Готово',
          )
        }} />
    </div>
  )
}

function Lines({ lines }: { lines: PayrollLine[] }) {
  const [open, setOpen] = useState<number | null>(null)
  if (lines.length === 0) return <p className="text-sm text-ink-muted">Строк начисления нет.</p>
  const total = lines.reduce((sum, l) => sum + Number(l.amount), 0)
  return (
    <div className="card overflow-x-auto">
      <table className="data-table">
        <thead>
          <tr><th>Начисление</th><th className="text-right">Кол-во</th><th className="text-right">Ставка</th><th className="text-right">%</th><th className="text-right">База</th><th className="text-right">Сумма</th></tr>
        </thead>
        <tbody>
          {lines.map((l) => {
            const payments = l.metadata.payments ?? []
            const students = l.metadata.students ?? []
            const details = payments.length + students.length > 0
            return (
              <Fragment key={l.id}>
                <tr onClick={details ? () => setOpen(open === l.id ? null : l.id) : undefined} className={details ? 'cursor-pointer' : undefined}>
                  <td>
                    <p className="font-medium text-ink">{l.description}</p>
                    <p className="text-xs text-ink-muted">{l.line_type_display}{details ? ` · ${open === l.id ? 'скрыть' : 'показать'} основание` : ''}</p>
                  </td>
                  <td className="text-right">{l.quantity !== null ? Number(l.quantity) : '—'}</td>
                  <td className="text-right">{l.rate !== null ? som(l.rate) : '—'}</td>
                  <td className="text-right">{l.percentage !== null ? Number(l.percentage) : '—'}</td>
                  <td className="text-right">{l.base_amount !== null ? som(l.base_amount) : '—'}</td>
                  <td className="text-right font-medium">{som(l.amount)}</td>
                </tr>
                {open === l.id ? (
                  <tr>
                    <td colSpan={6} className="bg-surface-muted text-xs">
                      {payments.length ? (
                        <table className="w-full">
                          <thead><tr className="text-ink-muted"><th className="text-left">Студент</th><th className="text-left">Поступил</th><th className="text-left">Обучение</th><th className="text-right">Платёж</th><th className="text-right">Учтено</th></tr></thead>
                          <tbody>
                            {payments.map((pay) => (
                              <tr key={pay.id}>
                                <td>{pay.student}</td><td>{formatDate(pay.received_date)}</td>
                                <td>{formatDate(pay.service_start)}–{formatDate(pay.service_end)}</td>
                                <td className="text-right">{som(pay.amount)}</td><td className="text-right">{som(pay.counted)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      ) : null}
                      {students.length ? (
                        <ul className="columns-2 sm:columns-3">
                          {students.map((st) => <li key={st.id}>{st.name} — {st.days} дн.</li>)}
                        </ul>
                      ) : null}
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            )
          })}
          <tr><td colSpan={5} className="text-right font-semibold">Итого начислено</td><td className="text-right font-semibold">{som(total.toFixed(2))}</td></tr>
        </tbody>
      </table>
    </div>
  )
}

function AuditList({ entries }: { entries: AuditEntry[] }) {
  if (entries.length === 0) return <p className="text-sm text-ink-muted">Записей нет.</p>
  return (
    <ul className="space-y-2">
      {entries.map((e) => (
        <li key={e.id} className="rounded-lg border border-border bg-surface p-3 text-sm">
          <div className="flex flex-wrap justify-between gap-2">
            <span className="font-medium text-ink">
              {ACTION_LABEL[e.action] ?? e.action} · {ENTITY_LABEL[e.entity_type] ?? e.entity_type}
            </span>
            <span className="text-xs text-ink-muted">{formatDateTime(e.created_at)} · {e.actor_name}</span>
          </div>
          {e.reason ? <p className="mt-1 text-ink-secondary">Причина: {e.reason}</p> : null}
          {'amount_due' in e.new_values ? (
            <p className="mt-1 text-xs text-ink-muted">
              Остаток: {som(String(e.old_values.amount_due ?? '')) } → {som(String(e.new_values.amount_due))}
            </p>
          ) : null}
        </li>
      ))}
    </ul>
  )
}

function PaymentModal({ payroll, isOpen, onClose, onSubmit, methods }: {
  payroll: PayrollDetail
  isOpen: boolean
  onClose: () => void
  methods: { value: string; label: string }[]
  onSubmit: (body: { amount: string; payment_date: string; payment_method: string; reference: string; comment: string; is_advance: boolean }, key: string) => Promise<boolean>
}) {
  const [form, setForm] = useState({ amount: '', payment_date: today(), payment_method: 'bank', reference: '', comment: '', is_advance: false })
  const [key, setKey] = useState(newIdempotencyKey)
  const [busy, setBusy] = useState(false)
  const amount = Number(form.amount)
  const tooMuch = amount > Number(payroll.amount_due)
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Зарегистрировать выплату">
      <p className="mb-4 text-sm text-ink-secondary">Остаток к выплате: <b>{som(payroll.amount_due)}</b></p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Сумма, сом" required htmlFor="pay-amount" error={tooMuch ? 'Больше остатка' : undefined}>
          <Input id="pay-amount" type="number" min="0.01" step="0.01" value={form.amount}
            onChange={(e) => setForm({ ...form, amount: e.target.value })} />
        </Field>
        <Field label="Дата выплаты" required htmlFor="pay-date">
          <Input id="pay-date" type="date" value={form.payment_date} onChange={(e) => setForm({ ...form, payment_date: e.target.value })} />
        </Field>
        <Field label="Способ" htmlFor="pay-method">
          <Select id="pay-method" value={form.payment_method} options={methods}
            onChange={(e) => setForm({ ...form, payment_method: e.target.value })} />
        </Field>
        <Field label="Номер документа" htmlFor="pay-ref">
          <Input id="pay-ref" value={form.reference} onChange={(e) => setForm({ ...form, reference: e.target.value })} />
        </Field>
      </div>
      <Field label="Комментарий" htmlFor="pay-comment" className="mt-3">
        <Textarea id="pay-comment" rows={2} value={form.comment} onChange={(e) => setForm({ ...form, comment: e.target.value })} />
      </Field>
      <label className="mt-3 flex items-center gap-2 text-sm">
        <input type="checkbox" checked={form.is_advance} onChange={(e) => setForm({ ...form, is_advance: e.target.checked })} />
        Аванс (частичная выплата)
      </label>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Отмена</Button>
        <Button
          isLoading={busy}
          disabled={!(amount > 0) || tooMuch || !form.payment_date}
          onClick={async () => {
            setBusy(true)
            const ok = await onSubmit(form, key)
            setBusy(false)
            if (ok) {
              setKey(newIdempotencyKey())
              setForm({ ...form, amount: '', reference: '', comment: '', is_advance: false })
              onClose()
            }
          }}
        >
          Зарегистрировать
        </Button>
      </div>
    </Modal>
  )
}

function AdjustmentModal({ isOpen, onClose, onSubmit, kinds, locked }: {
  isOpen: boolean
  onClose: () => void
  kinds: { value: string; label: string }[]
  locked: boolean
  onSubmit: (body: { kind: string; amount: string; reason: string }) => Promise<boolean>
}) {
  const [form, setForm] = useState({ kind: 'BONUS', amount: '', reason: '' })
  const [busy, setBusy] = useState(false)
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Добавить корректировку">
      {locked ? (
        <p className="mb-3 text-sm text-warning">Начисление уже утверждено — корректировка вступит в силу после утверждения директором.</p>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Тип" htmlFor="adj-kind">
          <Select id="adj-kind" value={form.kind} options={kinds} onChange={(e) => setForm({ ...form, kind: e.target.value })} />
        </Field>
        <Field label="Сумма, сом" required htmlFor="adj-amount"
          help={form.kind === 'CORRECTION' ? 'Со знаком: −500 уменьшает начисление' : 'Положительное число'}>
          <Input id="adj-amount" type="number" step="0.01" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
        </Field>
      </div>
      <Field label="Причина" required htmlFor="adj-reason" className="mt-3">
        <Textarea id="adj-reason" rows={3} value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
      </Field>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Отмена</Button>
        <Button isLoading={busy} disabled={!form.amount || !form.reason.trim()}
          onClick={async () => {
            setBusy(true)
            const ok = await onSubmit(form)
            setBusy(false)
            if (ok) {
              setForm({ kind: 'BONUS', amount: '', reason: '' })
              onClose()
            }
          }}>
          Добавить
        </Button>
      </div>
    </Modal>
  )
}
