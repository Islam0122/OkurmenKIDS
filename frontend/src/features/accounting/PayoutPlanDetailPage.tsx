import { Fragment, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ChevronDown, ChevronRight, FileDown, Plus } from 'lucide-react'

import { accountingApi, newIdempotencyKey } from '@/api/accounting'
import { PageHeader } from '@/components/layout/PageHeader'
import { BackLink } from '@/components/ui/BackLink'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { StatCard } from '@/components/ui/StatCard'
import { StatGrid } from '@/components/ui/StatGrid'
import { Textarea } from '@/components/ui/Textarea'
import { Field } from '@/features/worklog/formUi'
import { useAccountingMutation, useAccountingOptions, usePayoutPlan } from '@/hooks/useAccounting'
import type { PayoutPlanDetail, PayoutPlanLine } from '@/types/accounting'

import { CandidatePicker, PayoutStatusBadge, Readiness } from './PayoutPlanPage'
import { MONTHS, ReasonModal, Section, formatDate, formatDateTime, som, today, useRunner } from './shared'

const ACTION_LABELS: Record<string, string> = {
  create: 'Создан план',
  update: 'Изменён план',
  change_prepared: 'Изменены подготовленные средства',
  change_date: 'Изменена дата выплаты',
  add_line: 'Добавлено начисление',
  update_line: 'Изменена сумма строки',
  remove_line: 'Исключено начисление',
  approve: 'План утверждён',
  pay_line: 'Зарегистрирована выплата',
  cancel: 'План отменён',
}

export function PayoutPlanDetailPage() {
  const { id } = useParams()
  const planId = Number(id)
  const plan = usePayoutPlan(planId)
  const options = useAccountingOptions()
  const { run } = useRunner()
  const mutate = useAccountingMutation((fn: () => Promise<unknown>) => fn())
  const [editing, setEditing] = useState(false)
  const [adding, setAdding] = useState(false)
  const [paying, setPaying] = useState<PayoutPlanLine | null>(null)
  const [removing, setRemoving] = useState<PayoutPlanLine | null>(null)
  const [cancelling, setCancelling] = useState(false)
  const [open, setOpen] = useState<Record<number, boolean>>({})

  if (plan.isLoading) return <LoadingState />
  if (plan.isError || !plan.data) return <ErrorState onRetry={() => plan.refetch()} />
  const p = plan.data
  const t = p.totals
  const canEdit = options.data?.can_operate ?? false
  const draft = p.state === 'DRAFT'
  const approved = p.state === 'APPROVED'

  return (
    <div>
      <BackLink to="/accounting/payout-plan">К плану выплат</BackLink>
      <PageHeader
        title={p.title}
        description={`Выплата ${formatDate(p.payout_date)} · начисления за ${MONTHS[p.month - 1].toLowerCase()} ${p.year} · создал ${p.created_by_name}${p.approved_by_name ? ` · утвердил ${p.approved_by_name} ${formatDateTime(p.approved_at)}` : ''}`}
        actions={(
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" leftIcon={<FileDown className="size-4" />} onClick={() => run(() => accountingApi.downloadPayoutPlan(p.id, 'xlsx'))}>Excel</Button>
            <Button variant="ghost" leftIcon={<FileDown className="size-4" />} onClick={() => run(() => accountingApi.downloadPayoutPlan(p.id, 'pdf'))}>PDF</Button>
            {canEdit && p.state !== 'CANCELLED' ? <Button variant="secondary" onClick={() => setEditing(true)}>Изменить</Button> : null}
            {canEdit && draft ? (
              <Button disabled={!p.lines.length}
                onClick={() => run(() => mutate.mutateAsync(() => accountingApi.approvePayoutPlan(p.id, p.version)), 'План утверждён')}>
                Утвердить
              </Button>
            ) : null}
            {canEdit && p.state !== 'CANCELLED' && t.status !== 'PAID'
              ? <Button variant="danger" onClick={() => setCancelling(true)}>Отменить план</Button> : null}
          </div>
        )}
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <PayoutStatusBadge status={t.status} label={t.status_display} />
        {p.state !== 'CANCELLED' && p.lines.length ? <Readiness percent={t.readiness_percent} /> : null}
        {p.state === 'CANCELLED' ? (
          <p className="text-sm text-ink-secondary">
            Отменён {formatDateTime(p.cancelled_at)} ({p.cancelled_by_name}): {p.cancel_reason}. Начисления и выплаты сохранены.
          </p>
        ) : null}
        {draft ? <p className="text-sm text-ink-secondary">Черновик: состав можно менять; выплаты — после утверждения.</p> : null}
      </div>

      <StatGrid columns={3}>
        <StatCard label="Запланировано" value={som(t.planned)} hint={`Сотрудников: ${t.employees}`} />
        <StatCard label="Подготовлено" value={som(t.prepared)} hint="Внесено бухгалтером, это не выплата" />
        <StatCard label="Дефицит" value={som(t.deficit)} tone={Number(t.deficit) > 0 && p.state !== 'CANCELLED' ? 'danger' : 'default'}
          hint={`Осталось выплатить ${som(t.remaining)}`} />
        <StatCard label="Выплачено по плану" value={som(t.paid)} />
      </StatGrid>
      {p.comment ? <p className="mt-4 whitespace-pre-line rounded-lg bg-surface-muted p-3 text-sm text-ink-secondary">{p.comment}</p> : null}

      <Section title="Сотрудники в плане"
        actions={canEdit && draft ? <Button size="sm" variant="secondary" leftIcon={<Plus className="size-4" />} onClick={() => setAdding(true)}>Добавить начисления</Button> : null}>
        {!p.lines.length ? <EmptyState title="В плане нет начислений" description={canEdit && draft ? 'Добавьте утверждённые начисления с остатком.' : undefined} /> : (
          <div className="card overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th /><th>Сотрудник</th><th>Начисление</th>
                  <th className="text-right">Начислено</th><th className="text-right">Выплачено ранее</th>
                  <th className="text-right">По плану</th><th className="text-right">Остаток после плана</th><th>Статус</th><th />
                </tr>
              </thead>
              <tbody>
                {p.lines.map((line) => (
                  <Fragment key={line.id}>
                    <tr>
                      <td>
                        <button type="button" aria-label={open[line.id] ? 'Скрыть расчёт' : 'Почему такая сумма'}
                          onClick={() => setOpen({ ...open, [line.id]: !open[line.id] })} className="text-ink-muted hover:text-ink">
                          {open[line.id] ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                        </button>
                      </td>
                      <td>
                        {line.employee_name}
                        <p className="text-xs text-ink-muted">{[line.position, line.department_display, line.subjects.join(', ')].filter(Boolean).join(' · ')}</p>
                      </td>
                      <td className="whitespace-nowrap text-sm">{line.period_label}<p className="text-xs text-ink-muted">{line.salary_type_display}</p></td>
                      <td className="whitespace-nowrap text-right">{som(line.accrued)}</td>
                      <td className="whitespace-nowrap text-right">{som(line.paid_before)}</td>
                      <td className="whitespace-nowrap text-right">
                        {som(line.planned_amount)}
                        {Number(line.paid_by_plan) > 0 ? <p className="text-xs text-ink-muted">выплачено {som(line.paid_by_plan)}</p> : null}
                      </td>
                      <td className="whitespace-nowrap text-right">{som(line.due_after_plan)}</td>
                      <td className="text-sm">{line.status_display}</td>
                      <td className="whitespace-nowrap text-right">
                        {canEdit && approved && Number(line.remaining_in_plan) > 0
                          ? <Button size="sm" onClick={() => setPaying(line)}>Выплатить</Button> : null}
                        {canEdit && draft ? <Button size="sm" variant="ghost" onClick={() => setRemoving(line)}>Исключить</Button> : null}
                      </td>
                    </tr>
                    {open[line.id] ? (
                      <tr>
                        <td />
                        <td colSpan={8} className="bg-surface-muted text-sm">
                          <p className="font-medium text-ink">Почему запланировано {som(line.planned_amount)}</p>
                          <ul className="mt-1 space-y-0.5 text-ink-secondary">
                            {line.basis.map((b, i) => <li key={i}>{b.description}: {som(b.amount)}</li>)}
                            <li>Подтверждённое начисление (с корректировками): {som(line.accrued)}</li>
                            <li>Выплачено ранее (вне этого плана): {som(line.paid_before)}</li>
                            <li>Остаток до плана = начислено − выплачено ранее: {som((Number(line.accrued) - Number(line.paid_before)).toFixed(2))}; в план включено {som(line.planned_amount)}{Number(line.due_after_plan) > 0 ? `, после плана останется ${som(line.due_after_plan)}` : ''}</li>
                            <li>Статус начисления: {line.payroll_status_display}{line.planned_payment_date ? ` · плановая дата по правилу ${formatDate(line.planned_payment_date)}` : ''}</li>
                            {line.comment ? <li>Комментарий: {line.comment}</li> : null}
                          </ul>
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section title="История изменений">
        {!p.history.length ? <p className="text-sm text-ink-secondary">Записей нет.</p> : (
          <ul className="card divide-y divide-border">
            {p.history.map((h) => (
              <li key={h.id} className="px-4 py-2.5 text-sm">
                <span className="text-ink-muted">{formatDateTime(h.created_at)}</span> · <b>{ACTION_LABELS[h.action] ?? h.action}</b> · {h.actor_name}
                {h.reason ? <p className="text-ink-secondary">Причина: {h.reason}</p> : null}
                <HistoryDetails values={h.new_values} old={h.old_values} />
              </li>
            ))}
          </ul>
        )}
      </Section>

      {editing ? <EditPlanModal plan={p} onClose={() => setEditing(false)} /> : null}
      {adding ? <AddLinesModal plan={p} onClose={() => setAdding(false)} /> : null}
      {paying ? <PayLineModal plan={p} line={paying} methods={options.data?.payment_methods ?? []} onClose={() => setPaying(null)} /> : null}
      <ReasonModal isOpen={removing !== null} title={`Исключить: ${removing?.employee_name ?? ''}`} confirmLabel="Исключить"
        description="Строка останется в истории плана; остаток начисления снова можно будет запланировать."
        onClose={() => setRemoving(null)}
        onConfirm={(reason) => run(() => mutate.mutateAsync(() => accountingApi.updatePayoutLine(p.id, removing!.id, { version: p.version, remove: true, reason })), 'Начисление исключено')} />
      <ReasonModal isOpen={cancelling} title="Отменить план" tone="danger" confirmLabel="Отменить план"
        description="Начисления и уже зарегистрированные выплаты не удаляются и не меняются. Невыплаченный остаток освободится для других планов."
        onClose={() => setCancelling(false)}
        onConfirm={(reason) => run(() => mutate.mutateAsync(() => accountingApi.cancelPayoutPlan(p.id, p.version, reason)), 'План отменён')} />
    </div>
  )
}

const FIELD_LABELS: Record<string, string> = {
  prepared_amount: 'подготовлено', payout_date: 'дата', title: 'название', comment: 'комментарий', amount: 'сумма',
  employee_name: 'сотрудник', planned: 'запланировано', prepared: 'подготовлено', payment_date: 'дата выплаты', month: 'месяц', year: 'год',
}

function HistoryDetails({ values, old }: { values: Record<string, unknown>; old: Record<string, unknown> }) {
  const keys = Object.keys(values).filter((k) => k in FIELD_LABELS && values[k] !== '' && values[k] !== null)
  if (!keys.length) return null
  return (
    <p className="text-xs text-ink-muted">
      {keys.map((k) => `${FIELD_LABELS[k]}: ${k in old ? `${String(old[k])} → ` : ''}${String(values[k])}`).join(' · ')}
    </p>
  )
}

function EditPlanModal({ plan, onClose }: { plan: PayoutPlanDetail; onClose: () => void }) {
  const draft = plan.state === 'DRAFT'
  const [form, setForm] = useState({
    title: plan.title, payout_date: plan.payout_date, prepared_amount: plan.prepared_amount, comment: plan.comment, reason: '',
  })
  const { run, busy } = useRunner()
  const mutate = useAccountingMutation((fn: () => Promise<unknown>) => fn())
  const dateChanged = form.payout_date !== plan.payout_date
  const needsReason = !draft && dateChanged
  const submit = () => run(async () => {
    const body: Record<string, unknown> & { version: number } = { version: plan.version, reason: form.reason.trim() }
    if (draft && form.title !== plan.title) body.title = form.title.trim()
    if (dateChanged) body.payout_date = form.payout_date
    if (Number(form.prepared_amount) !== Number(plan.prepared_amount)) body.prepared_amount = form.prepared_amount || '0'
    if (form.comment !== plan.comment) body.comment = form.comment
    await mutate.mutateAsync(() => accountingApi.updatePayoutPlan(plan.id, body))
    onClose()
  }, 'План сохранён')
  return (
    <Modal isOpen onClose={onClose} title="Изменить план">
      <div className="grid gap-3 sm:grid-cols-2">
        {draft ? (
          <Field label="Название" required htmlFor="ep-title" className="sm:col-span-2">
            <Input id="ep-title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
          </Field>
        ) : null}
        <Field label="Дата выплаты" required htmlFor="ep-date">
          <Input id="ep-date" type="date" value={form.payout_date} onChange={(e) => setForm({ ...form, payout_date: e.target.value })} />
        </Field>
        <Field label="Подготовлено средств, сом" htmlFor="ep-prepared" help="Не создаёт выплат">
          <Input id="ep-prepared" type="number" min="0" step="0.01" value={form.prepared_amount}
            onChange={(e) => setForm({ ...form, prepared_amount: e.target.value })} />
        </Field>
      </div>
      <Field label="Комментарий" htmlFor="ep-comment" className="mt-3">
        <Textarea id="ep-comment" rows={2} value={form.comment} onChange={(e) => setForm({ ...form, comment: e.target.value })} />
      </Field>
      <Field label="Причина изменения" required={needsReason} htmlFor="ep-reason" className="mt-3" help="Сохраняется в истории плана">
        <Textarea id="ep-reason" rows={2} value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
      </Field>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Отмена</Button>
        <Button isLoading={busy} disabled={!form.payout_date || Number(form.prepared_amount) < 0 || (needsReason && !form.reason.trim()) || (draft && !form.title.trim())}
          onClick={submit}>Сохранить</Button>
      </div>
    </Modal>
  )
}

function AddLinesModal({ plan, onClose }: { plan: PayoutPlanDetail; onClose: () => void }) {
  const [selected, setSelected] = useState<Record<number, string>>({})
  const [period, setPeriod] = useState({ year: plan.year, month: plan.month })
  const { run, busy } = useRunner()
  const mutate = useAccountingMutation((fn: () => Promise<unknown>) => fn())
  const valid = Object.keys(selected).length > 0 && Object.values(selected).every((v) => Number(v) > 0)
  return (
    <Modal isOpen onClose={onClose} size="lg" title="Добавить начисления">
      <div className="mb-3 flex gap-2">
        <Select aria-label="Месяц начислений" value={String(period.month)} options={MONTHS.map((label, i) => ({ value: String(i + 1), label }))}
          onChange={(e) => { setPeriod({ ...period, month: Number(e.target.value) }); setSelected({}) }} />
        <Input aria-label="Год начислений" type="number" className="w-28" value={period.year}
          onChange={(e) => { setPeriod({ ...period, year: Number(e.target.value) }); setSelected({}) }} />
      </div>
      <CandidatePicker year={period.year} month={period.month} selected={selected} onChange={setSelected} />
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Отмена</Button>
        <Button isLoading={busy} disabled={!valid} onClick={() => run(async () => {
          await mutate.mutateAsync(() => accountingApi.addPayoutLines(plan.id, plan.version,
            Object.entries(selected).map(([payroll, amount]) => ({ payroll: Number(payroll), amount }))))
          onClose()
        }, 'Начисления добавлены')}>Добавить</Button>
      </div>
    </Modal>
  )
}

function PayLineModal({ plan, line, methods, onClose }: {
  plan: PayoutPlanDetail
  line: PayoutPlanLine
  methods: { value: string; label: string }[]
  onClose: () => void
}) {
  const [form, setForm] = useState({
    amount: line.remaining_in_plan, payment_date: plan.payout_date <= today() ? plan.payout_date : today(),
    payment_method: 'bank', reference: '', comment: '',
  })
  const [key] = useState(newIdempotencyKey)
  const { run, busy } = useRunner()
  const mutate = useAccountingMutation((fn: () => Promise<unknown>) => fn())
  const amount = Number(form.amount)
  const tooMuch = amount > Number(line.remaining_in_plan)
  return (
    <Modal isOpen onClose={onClose} title={`Выплата: ${line.employee_name}`}>
      <p className="mb-4 text-sm text-ink-secondary">
        Осталось выплатить по плану: <b>{som(line.remaining_in_plan)}</b>. Выплата регистрируется в начислении «{line.period_label}» тем же механизмом, что и обычная выплата.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Сумма, сом" required htmlFor="pl-amount" error={tooMuch ? 'Больше остатка по плану' : undefined}>
          <Input id="pl-amount" type="number" min="0.01" step="0.01" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
        </Field>
        <Field label="Дата выплаты" required htmlFor="pl-date">
          <Input id="pl-date" type="date" value={form.payment_date} onChange={(e) => setForm({ ...form, payment_date: e.target.value })} />
        </Field>
        <Field label="Способ" htmlFor="pl-method">
          <Select id="pl-method" value={form.payment_method} options={methods} onChange={(e) => setForm({ ...form, payment_method: e.target.value })} />
        </Field>
        <Field label="Номер документа" htmlFor="pl-ref">
          <Input id="pl-ref" value={form.reference} onChange={(e) => setForm({ ...form, reference: e.target.value })} />
        </Field>
      </div>
      <Field label="Комментарий" htmlFor="pl-comment" className="mt-3">
        <Textarea id="pl-comment" rows={2} value={form.comment} onChange={(e) => setForm({ ...form, comment: e.target.value })} />
      </Field>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Отмена</Button>
        <Button isLoading={busy} disabled={!(amount > 0) || tooMuch || !form.payment_date} onClick={() => run(async () => {
          await mutate.mutateAsync(() => accountingApi.payPlanLine(plan.id, line.id, form, key))
          onClose()
        }, 'Выплата зарегистрирована')}>Зарегистрировать выплату</Button>
      </div>
    </Modal>
  )
}
