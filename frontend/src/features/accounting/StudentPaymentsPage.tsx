import { useEffect, useState } from 'react'
import { Plus } from 'lucide-react'

import { accountingApi, newIdempotencyKey } from '@/api/accounting'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { useAccountingMutation, useAccountingOptions, useStudentPayments } from '@/hooks/useAccounting'
import { Field } from '@/features/worklog/formUi'
import type { AccountingOptions, StudentPayment, StudentRef } from '@/types/accounting'

import { ReasonModal, formatDate, som, today, useRunner } from './shared'

function monthRange(date: string): [string, string] {
  const [y, m] = date.split('-').map(Number)
  const last = new Date(y, m, 0).getDate()
  const mm = String(m).padStart(2, '0')
  return [`${y}-${mm}-01`, `${y}-${mm}-${String(last).padStart(2, '0')}`]
}

export function StudentPaymentsPage() {
  const [filters, setFilters] = useState<{ search?: string; group?: number; kind?: string; status?: string; date_from?: string; date_to?: string; page?: number }>({})
  const payments = useStudentPayments(filters)
  const options = useAccountingOptions()
  const { showToast } = useToast()
  const { run } = useRunner()
  const mutate = useAccountingMutation(async (fn: () => Promise<unknown>) => fn())
  const [creating, setCreating] = useState<null | { refundOf?: StudentPayment }>(null)
  const [voiding, setVoiding] = useState<StudentPayment | null>(null)
  const canEdit = options.data?.can_operate ?? false

  return (
    <div>
      <PageHeader
        title="Платежи студентов"
        description="Фактические оплаты и возвраты — база для процента тренеров. Платежи не удаляются: ошибочный отменяется с причиной."
        actions={canEdit ? <Button leftIcon={<Plus className="size-4" />} onClick={() => setCreating({})}>Внести платёж</Button> : null}
      />
      <FilterBar>
        <FilterField size="lg">
          <SearchInput value={filters.search ?? ''} placeholder="Студент или номер документа"
            onChange={(v) => setFilters({ ...filters, search: v || undefined, page: undefined })} />
        </FilterField>
        <FilterField>
          <Select aria-label="Группа" value={filters.group ? String(filters.group) : ''} placeholder="Все группы"
            options={(options.data?.groups ?? []).map((g) => ({ value: String(g.id), label: g.name }))}
            onChange={(e) => setFilters({ ...filters, group: Number(e.target.value) || undefined, page: undefined })} />
        </FilterField>
        <FilterField>
          <Select aria-label="Тип" value={filters.kind ?? ''} placeholder="Оплаты и возвраты"
            options={[{ value: 'payment', label: 'Оплаты' }, { value: 'refund', label: 'Возвраты' }]}
            onChange={(e) => setFilters({ ...filters, kind: e.target.value || undefined, page: undefined })} />
        </FilterField>
        <FilterField label="С" htmlFor="sp-from">
          <Input id="sp-from" type="date" value={filters.date_from ?? ''} onChange={(e) => setFilters({ ...filters, date_from: e.target.value || undefined })} />
        </FilterField>
        <FilterField label="По" htmlFor="sp-to">
          <Input id="sp-to" type="date" value={filters.date_to ?? ''} onChange={(e) => setFilters({ ...filters, date_to: e.target.value || undefined })} />
        </FilterField>
      </FilterBar>

      {payments.isLoading ? <LoadingState /> : payments.isError ? <ErrorState onRetry={() => payments.refetch()} /> :
        payments.data?.results.length === 0 ? <EmptyState title="Платежей нет" /> : (
          <div className="card overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr><th>Дата</th><th>Студент</th><th>Группа</th><th>Обучение</th><th className="text-right">Сумма</th><th>Способ</th><th>Статус</th><th /></tr>
              </thead>
              <tbody>
                {payments.data?.results.map((p) => (
                  <tr key={p.id} className={p.status === 'void' ? 'opacity-60' : undefined}>
                    <td>{formatDate(p.received_date)}</td>
                    <td>{p.student_name}{p.reference ? <p className="text-xs text-ink-muted">№ {p.reference}</p> : null}</td>
                    <td>{p.group_name}<p className="text-xs text-ink-muted">{p.course_name}</p></td>
                    <td className="whitespace-nowrap text-sm">{formatDate(p.service_start)}–{formatDate(p.service_end)}</td>
                    <td className="text-right">
                      {p.kind === 'refund' ? <span className="text-danger">−{som(p.amount)}</span> : som(p.amount)}
                      {p.kind === 'payment' && Number(p.refunded_amount) > 0 ? <p className="text-xs text-ink-muted">возвращено {som(p.refunded_amount)}</p> : null}
                    </td>
                    <td>{p.method_display}</td>
                    <td>
                      <Badge tone={p.status === 'void' ? 'muted' : p.kind === 'refund' ? 'warning' : 'success'}>
                        {p.status === 'void' ? 'Отменён' : p.kind_display}
                      </Badge>
                      {p.void_reason ? <p className="text-xs text-ink-muted">{p.void_reason}</p> : null}
                    </td>
                    <td className="whitespace-nowrap text-right">
                      {canEdit && p.status === 'confirmed' ? (
                        <>
                          {p.kind === 'payment' ? <Button size="sm" variant="ghost" onClick={() => setCreating({ refundOf: p })}>Возврат</Button> : null}
                          <Button size="sm" variant="ghost" onClick={() => setVoiding(p)}>Отменить</Button>
                        </>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      {payments.data && (payments.data.next || payments.data.previous) ? (
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" size="sm" disabled={!payments.data.previous} onClick={() => setFilters({ ...filters, page: (filters.page ?? 1) - 1 })}>Назад</Button>
          <Button variant="ghost" size="sm" disabled={!payments.data.next} onClick={() => setFilters({ ...filters, page: (filters.page ?? 1) + 1 })}>Далее</Button>
        </div>
      ) : null}

      {creating && options.data ? <PaymentForm options={options.data} refundOf={creating.refundOf} onClose={() => setCreating(null)} /> : null}
      <ReasonModal isOpen={voiding !== null} title="Отменить платёж" tone="danger" confirmLabel="Отменить платёж"
        description="Платёж останется в истории со статусом «Отменён» и перестанет учитываться в новых расчётах."
        onClose={() => setVoiding(null)}
        onConfirm={(reason) => run(async () => {
          const result = await mutate.mutateAsync(() => accountingApi.voidStudentPayment(voiding!.id, reason)) as StudentPayment
          if (result.affected_payrolls?.length) {
            showToast(`Платёж входил в утверждённые начисления (${result.affected_payrolls.length}) — при необходимости оформите корректировку.`, 'info')
          }
        }, 'Платёж отменён')} />
    </div>
  )
}

function PaymentForm({ options, refundOf, onClose }: { options: AccountingOptions; refundOf?: StudentPayment; onClose: () => void }) {
  const [search, setSearch] = useState('')
  const [found, setFound] = useState<StudentRef[]>([])
  const [student, setStudent] = useState<StudentRef | null>(null)
  const [first, last] = monthRange(today())
  const [form, setForm] = useState({
    group: '', amount: '', received_date: today(), service_start: first, service_end: last, method: 'cash', reference: '', comment: '',
  })
  const [key] = useState(newIdempotencyKey)
  const { run, busy } = useRunner()
  const mutate = useAccountingMutation(async (fn: () => Promise<unknown>) => fn())

  useEffect(() => {
    if (refundOf || search.trim().length < 2) {
      setFound([])
      return
    }
    const timer = setTimeout(() => { void accountingApi.students(search).then(setFound) }, 250)
    return () => clearTimeout(timer)
  }, [search, refundOf])

  const submit = () => run(() => mutate.mutateAsync(() => accountingApi.createStudentPayment(
    refundOf
      ? { student: refundOf.student, amount: form.amount, received_date: form.received_date, refund_of: refundOf.id, method: form.method, reference: form.reference, comment: form.comment }
      : {
        student: student!.id, group: form.group ? Number(form.group) : student!.group, amount: form.amount,
        received_date: form.received_date, service_start: form.service_start, service_end: form.service_end,
        method: form.method, reference: form.reference, comment: form.comment,
      },
    key,
  )), refundOf ? 'Возврат оформлен' : 'Платёж внесён')

  const ready = Number(form.amount) > 0 && (refundOf || (student && (form.group || student.group)))
  return (
    <Modal isOpen onClose={onClose} title={refundOf ? `Возврат по платежу от ${formatDate(refundOf.received_date)}` : 'Платёж студента'} size="lg">
      {refundOf ? (
        <p className="mb-3 text-sm text-ink-secondary">
          {refundOf.student_name} · {refundOf.group_name} · платёж {som(refundOf.amount)}
          {Number(refundOf.refunded_amount) > 0 ? `, уже возвращено ${som(refundOf.refunded_amount)}` : ''}
        </p>
      ) : (
        <div className="mb-3">
          {student ? (
            <div className="flex items-center justify-between rounded-lg border border-border p-3 text-sm">
              <span><b>{student.name}</b> · {student.group_name ?? 'без группы'}</span>
              <Button size="sm" variant="ghost" onClick={() => setStudent(null)}>Изменить</Button>
            </div>
          ) : (
            <Field label="Студент" required>
              <SearchInput value={search} onChange={setSearch} placeholder="Начните вводить имя" />
              {found.length ? (
                <ul className="mt-1 max-h-48 overflow-y-auto rounded-lg border border-border">
                  {found.map((s) => (
                    <li key={s.id}>
                      <button type="button" className="w-full px-3 py-2 text-left text-sm hover:bg-surface-hover"
                        onClick={() => { setStudent(s); setForm({ ...form, group: s.group ? String(s.group) : '' }) }}>
                        {s.name} <span className="text-ink-muted">· {s.group_name ?? 'без группы'}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </Field>
          )}
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        {!refundOf ? (
          <Field label="Группа" required htmlFor="sp-group">
            <Select id="sp-group" value={form.group} placeholder="Выберите группу"
              options={options.groups.map((g) => ({ value: String(g.id), label: g.name }))}
              onChange={(e) => setForm({ ...form, group: e.target.value })} />
          </Field>
        ) : null}
        <Field label="Сумма, сом" required htmlFor="sp-amount">
          <Input id="sp-amount" type="number" min="0.01" step="0.01" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
        </Field>
        <Field label={refundOf ? 'Дата возврата' : 'Дата поступления'} required htmlFor="sp-date">
          <Input id="sp-date" type="date" value={form.received_date} onChange={(e) => setForm({ ...form, received_date: e.target.value })} />
        </Field>
        {!refundOf ? (
          <>
            <Field label="Обучение с" required htmlFor="sp-s">
              <Input id="sp-s" type="date" value={form.service_start} onChange={(e) => setForm({ ...form, service_start: e.target.value })} />
            </Field>
            <Field label="Обучение по" required htmlFor="sp-e" help="Оплата за несколько месяцев — один платёж с длинным периодом">
              <Input id="sp-e" type="date" value={form.service_end} onChange={(e) => setForm({ ...form, service_end: e.target.value })} />
            </Field>
          </>
        ) : null}
        <Field label="Способ" htmlFor="sp-method">
          <Select id="sp-method" value={form.method} options={options.student_payment_methods} onChange={(e) => setForm({ ...form, method: e.target.value })} />
        </Field>
        <Field label="Номер документа" htmlFor="sp-ref">
          <Input id="sp-ref" value={form.reference} onChange={(e) => setForm({ ...form, reference: e.target.value })} />
        </Field>
      </div>
      <Field label="Комментарий" htmlFor="sp-comment" className="mt-3">
        <Textarea id="sp-comment" rows={2} value={form.comment} onChange={(e) => setForm({ ...form, comment: e.target.value })} />
      </Field>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Отмена</Button>
        <Button isLoading={busy} disabled={!ready} onClick={async () => (await submit()) && onClose()}>
          {refundOf ? 'Оформить возврат' : 'Внести'}
        </Button>
      </div>
    </Modal>
  )
}
