import { useState } from 'react'
import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Banknote, FileText, RotateCcw, UserCheck } from 'lucide-react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'

import { financeApi } from '@/api/finance'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { BackLink } from '@/components/ui/BackLink'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { DataTable } from '@/components/ui/DataTable'
import { DatePicker } from '@/components/ui/DatePicker'
import { EmptyState } from '@/components/ui/EmptyState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { Tabs } from '@/components/ui/Tabs'
import { Textarea } from '@/components/ui/Textarea'
import { Notice } from '@/features/accounting/shared'
import { Field } from '@/features/worklog/formUi'
import type { ArchiveContract, ArchiveDetail, StudentFinance } from '@/types/finance'

import {
  Amount,
  ContractStatusBadge,
  FINANCE_KEY,
  InvoiceStatusBadge,
  Loadable,
  formatDate,
  formatDateTime,
  som,
  today,
  useFinanceMe,
  useInvalidateFinance,
  useRunner,
} from './ui'

type Tab = 'payments' | 'invoices' | 'contracts' | 'study'
const TABS: { key: Tab; label: string }[] = [
  { key: 'payments', label: 'История платежей' },
  { key: 'invoices', label: 'История начислений' },
  { key: 'contracts', label: 'Договоры' },
  { key: 'study', label: 'История обучения' },
]

function Info({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="field-label">{label}</dt>
      <dd className="mt-0.5 break-words text-sm text-ink">{children || '—'}</dd>
    </div>
  )
}

/** Блок «Финансы»: суммы по всем договорам студента (та же формула, что карточка договора). */
export function FinanceSummary({ finance }: { finance: StudentFinance }) {
  const cells: [string, string | null, 'danger' | 'muted' | 'brand' | undefined][] = [
    ['Стоимость договора', finance.contract_price, undefined],
    ['Начислено', finance.invoiced, undefined],
    ['Оплачено', finance.paid, 'brand'],
    ['Скидки', finance.discount, 'muted'],
    ['Остаток задолженности', finance.debt, finance.has_debt ? 'danger' : 'muted'],
    ['Переплата', finance.overpayment, Number(finance.overpayment) > 0 ? 'brand' : 'muted'],
  ]
  return (
    <dl className="grid gap-3 sm:grid-cols-3 xl:grid-cols-6">
      {cells.map(([label, value, tone]) => (
        <div key={label} className="rounded-lg bg-surface-muted px-3 py-2">
          <dt className="text-xs text-ink-secondary">{label}</dt>
          <dd className="mt-0.5 text-base"><Amount value={value} tone={tone} /></dd>
        </div>
      ))}
      {Number(finance.adjusted) > 0 ? (
        <p className="text-xs text-ink-secondary sm:col-span-3 xl:col-span-6">
          Корректировки / списания начислений: {som(finance.adjusted)}
        </p>
      ) : null}
    </dl>
  )
}

function PaymentsTable({ data }: { data: ArchiveDetail }) {
  if (!data.payments.length) return <EmptyState title="Платежей не было" />
  return (
    <DataTable rows={data.payments} getRowKey={(p) => p.id} columns={[
      { key: 'date', header: 'Дата платежа', render: (p) => <span className="whitespace-nowrap">{formatDate(p.date)}</span> },
      { key: 'amount', header: 'Сумма', render: (p) => (
        <div><Amount value={p.kind === 'refund' ? `-${p.amount}` : p.amount} tone={p.status === 'void' ? 'muted' : undefined} />
          {p.kind !== 'payment' ? <p className="text-xs text-ink-secondary">{p.kind_display}</p> : null}</div>
      ) },
      { key: 'method', header: 'Способ оплаты', render: (p) => p.method_display },
      { key: 'by', header: 'Кто принял', render: (p) => p.accepted_by?.name ?? '—' },
      { key: 'comment', header: 'Комментарий', render: (p) => <span className="text-sm">{p.comment || '—'}</span> },
      { key: 'tx', header: 'Транзакция', render: (p) => (
        <div className="text-sm">
          <Link to={`/finance/payments/${p.id}`} className="text-brand-700 hover:underline">{p.transaction}</Link>
          {p.reference ? <p className="text-xs text-ink-secondary">док. {p.reference}</p> : null}
          {p.receipt?.number ? <p className="text-xs text-ink-secondary">чек {p.receipt.number}</p> : null}
        </div>
      ) },
      { key: 'status', header: 'Статус', render: (p) => (
        <Badge tone={p.status === 'confirmed' ? 'success' : 'muted'}>{p.status_display}</Badge>
      ) },
    ]} />
  )
}

function InvoicesTable({ data }: { data: ArchiveDetail }) {
  if (!data.invoices.length) return <EmptyState title="Начислений не было" />
  return (
    <DataTable rows={data.invoices} getRowKey={(i) => i.id} columns={[
      { key: 'date', header: 'Дата начисления', render: (i) => <span className="whitespace-nowrap">{formatDate(i.date)}</span> },
      { key: 'reason', header: 'Причина начисления', render: (i) => (
        <div className="text-sm"><p>{i.reason}</p><p className="text-xs text-ink-secondary">{i.number ?? '—'} · договор №{i.contract}</p>
          {i.void_reason ? <p className="text-xs text-ink-secondary">{i.void_reason}</p> : null}</div>
      ) },
      { key: 'lessons', header: 'Занятий', render: (i) => <span className="tabular-nums">{i.lessons_used}/{i.lessons_total}</span> },
      { key: 'amount', header: 'Сумма', render: (i) => (
        <div><Amount value={i.amount} />
          {Number(i.balance) > 0 && i.status !== 'VOID' ? <p className="text-xs text-danger">остаток {som(i.balance)}</p> : null}</div>
      ) },
      { key: 'status', header: 'Статус', render: (i) => <InvoiceStatusBadge status={i.status} label={i.status_display} /> },
    ]} />
  )
}

function ContractBlock({ contract }: { contract: ArchiveContract }) {
  return (
    <Card title={<span>Договор №{contract.number} · {contract.subject ?? contract.plan}</span>}
      actions={<ContractStatusBadge status={contract.status} label={contract.status_display} />}>
      <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Info label="Программа">{contract.plan} · {contract.payment_mode_display}</Info>
        <Info label="Начало">{formatDate(contract.start_date)}</Info>
        <Info label="Начисления остановлены">
          {contract.stopped_on ? `${formatDate(contract.stopped_on)} · ${contract.stop_source_display}` : null}
        </Info>
        <Info label="Ответственный бухгалтер">{contract.responsible_accountant?.name}</Info>
        <Info label="Стандартная стоимость"><Amount value={contract.standard_course_price} /></Info>
        <Info label="Итоговая стоимость"><Amount value={contract.final_course_price} /></Info>
        <Info label="Скидка">
          <Amount value={contract.discount_amount} />{contract.discount_reason ? ` — ${contract.discount_reason}` : ''}
        </Info>
        <Info label="Родитель">{[contract.parent_name, contract.parent_phone].filter(Boolean).join(', ')}</Info>
      </dl>
      <div className="mt-4"><FinanceSummary finance={{ ...contract.totals, contracts_count: 1, has_debt: Number(contract.totals.debt) > 0 }} /></div>
      {contract.terms_history.length ? (
        <div className="mt-4">
          <p className="mb-2 text-sm font-medium text-ink">История изменений условий</p>
          <ul className="divide-y divide-border rounded-lg border border-border text-sm">
            {contract.terms_history.map((t) => (
              <li key={t.id} className="flex flex-wrap justify-between gap-2 px-3 py-2">
                <span>{formatDateTime(t.requested_at)} · {t.reason} · итог <Amount value={t.final_course_price} /> · скидка <Amount value={t.discount_amount} /></span>
                <span className="text-ink-secondary">{t.status_display}{t.decided_by ? ` · ${t.decided_by.name}` : ''}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {contract.adjustments.length ? (
        <div className="mt-4">
          <p className="mb-2 text-sm font-medium text-ink">Корректировки и списания</p>
          <ul className="divide-y divide-border rounded-lg border border-border text-sm">
            {contract.adjustments.map((a) => (
              <li key={a.id} className="flex flex-wrap justify-between gap-2 px-3 py-2">
                <span>{formatDate(a.date)} · {a.invoice} · <Amount value={a.amount} /> — {a.reason}</span>
                <span className="text-ink-secondary">{a.status_display}{a.created_by ? ` · ${a.created_by.name}` : ''}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {contract.documents.length ? (
        <div className="mt-4">
          <p className="mb-2 text-sm font-medium text-ink">Документы (чеки)</p>
          <div className="flex flex-wrap gap-2">
            {contract.documents.map((d) => (
              <Link key={d.id} to={`/finance/receipts/${d.id}`}
                className="inline-flex items-center gap-1 rounded-lg border border-border px-2.5 py-1 text-sm text-brand-700 hover:bg-surface-hover">
                <FileText className="size-4" aria-hidden />{d.number ?? `№${d.id}`} · {d.kind_display}
                {d.status_display !== 'Выдан' ? ` · ${d.status_display}` : ''}
              </Link>
            ))}
          </div>
        </div>
      ) : null}
      <div className="mt-4 flex flex-wrap gap-2">
        <Link to={`/finance/students/${contract.id}`} className="text-sm font-medium text-brand-700 hover:underline">
          Открыть карточку договора (корректировки, списание долга, аванс) →
        </Link>
      </div>
    </Card>
  )
}

function StudyBlock({ data }: { data: ArchiveDetail }) {
  const { study } = data
  return (
    <div className="space-y-4">
      <Card title="Обучение">
        <dl className="grid gap-3 sm:grid-cols-3">
          <Info label="Посещено занятий">{String(study.attended_lessons)}</Info>
          <Info label="Последнее посещение">{formatDate(study.last_attendance)}</Info>
          <Info label="Группы">{study.groups.map((g) => g.name).join(' → ')}</Info>
        </dl>
      </Card>
      <Card title="Переводы между группами">
        {study.transfers.length ? (
          <ul className="divide-y divide-border text-sm">
            {study.transfers.map((t) => (
              <li key={t.id} className="py-2">{formatDate(t.date)}: {t.from_group?.name ?? '—'} → {t.group?.name ?? '—'}
                {t.comment ? <span className="text-ink-secondary"> — {t.comment}</span> : null}
                {t.performed_by ? <span className="text-ink-secondary"> · {t.performed_by.name}</span> : null}</li>
            ))}
          </ul>
        ) : <p className="text-sm text-ink-secondary">Переводов не было.</p>}
      </Card>
      <Card title="История деактиваций и восстановлений">
        <ul className="divide-y divide-border text-sm">
          {data.status_history.map((e) => (
            <li key={e.id} className="flex flex-wrap justify-between gap-2 py-2">
              <span><b className="font-medium">{e.type_display}</b> · {formatDate(e.date)}{e.group ? ` · ${e.group.name}` : ''}
                {e.reason_display ? ` · ${e.reason_display}` : ''}{e.comment ? ` — ${e.comment}` : ''}</span>
              <span className="text-ink-secondary">{e.performed_by?.name ?? 'Система'}</span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  )
}

/** Восстановление: сначала проверки (группа, договор), затем подтверждение. */
function RestoreModal({ studentId, name, onClose }: { studentId: number; name: string; onClose: () => void }) {
  const check = useQuery({ queryKey: [...FINANCE_KEY, 'archive', studentId, 'restore-check'],
    queryFn: () => financeApi.restoreCheck(studentId) })
  const invalidate = useInvalidateFinance()
  const { run, busy } = useRunner()
  const navigate = useNavigate()
  const [group, setGroup] = useState('')
  const [date, setDate] = useState(today())
  const [comment, setComment] = useState('')

  async function submit() {
    const ok = await run(() => financeApi.restoreStudent(studentId, { group: Number(group), event_date: date || null, comment }),
      `${name}: студент восстановлен`)
    if (ok) {
      await invalidate()
      onClose()
      if (check.data?.needs_new_contract) navigate(`/finance/contracts/new?student=${studentId}`)
    }
  }

  return (
    <Modal isOpen onClose={onClose} title="Восстановить студента" size="lg" icon={<UserCheck className="size-5 text-brand-600" aria-hidden />}>
      {check.isLoading ? <LoadingState /> : check.data ? (
        <div className="space-y-4">
          <p className="text-sm text-ink-secondary">
            Статус станет «Активен». Платежи, договоры, начисления и история деактивации сохраняются;
            старые начисления повторно не создаются.
          </p>
          <Notice tone="warning" items={check.data.warnings} />
          {check.data.resumable_contracts.length ? (
            <p className="text-sm text-ink">Возобновятся договоры: {check.data.resumable_contracts
              .map((c) => `№${c.id} (${c.subject ?? c.plan})`).join(', ')}</p>
          ) : null}
          <Field label="Группа" htmlFor="restore-group" required>
            <Select id="restore-group" value={group} placeholder="Выберите группу" onChange={(e) => setGroup(e.target.value)}
              options={check.data.groups.map((g) => ({ value: String(g.id),
                label: `${g.name} — ${g.course} (${g.students_count}${g.max_students ? `/${g.max_students}` : ''})` }))} />
          </Field>
          <Field label="Дата возвращения" htmlFor="restore-date">
            <DatePicker id="restore-date" value={date} onChange={(e) => setDate(e.target.value)} />
          </Field>
          <Field label="Комментарий" htmlFor="restore-comment">
            <Textarea id="restore-comment" rows={2} value={comment} onChange={(e) => setComment(e.target.value)} />
          </Field>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={onClose}>Отмена</Button>
            <Button onClick={submit} isLoading={busy} disabled={!group || !check.data.can_restore}>
              {check.data.needs_new_contract ? 'Восстановить и оформить договор' : 'Подтвердить восстановление'}
            </Button>
          </div>
        </div>
      ) : <p className="text-sm text-danger">Не удалось выполнить проверки. Попробуйте ещё раз.</p>}
    </Modal>
  )
}

export function ArchiveStudentPage() {
  const { studentId } = useParams()
  const id = Number(studentId)
  const location = useLocation()
  const me = useFinanceMe()
  const [tab, setTab] = useState<Tab>('payments')
  const [restoring, setRestoring] = useState(false)
  const query = useQuery({ queryKey: [...FINANCE_KEY, 'archive', id], queryFn: () => financeApi.archiveStudent(id),
    enabled: Number.isFinite(id) })
  const back = (location.state as { from?: string } | null)?.from ?? '/finance/archive'

  return (
    <div>
      <BackLink to={back}>Архив студентов</BackLink>
      <Loadable query={query}>
        {(data) => {
          const { student, deactivation } = data
          // Принять оплату — по договору с долгом (иначе по последнему договору).
          const payContract = data.contracts.find((c) => Number(c.totals.debt) > 0) ?? data.contracts[0]
          return (
            <>
              <PageHeader title={student.name}
                badge={<Badge tone={student.is_archived ? 'muted' : 'success'}>
                  {student.is_archived ? 'Неактивен' : student.status_display}</Badge>}
                description={student.is_archived ? 'Студент в архиве: долг и история сохраняются.'
                  : 'Студент восстановлен — карточка показывает его историю.'}
                actions={
                  <div className="flex flex-wrap gap-2">
                    {me.data?.can_record_payments && payContract ? (
                      <Link to={`/finance/payments/new?profile=${payContract.id}`}>
                        <Button leftIcon={<Banknote className="size-4" />}>Принять оплату</Button>
                      </Link>
                    ) : null}
                    {data.can_restore && student.is_archived ? (
                      <Button variant="secondary" leftIcon={<RotateCcw className="size-4" />} onClick={() => setRestoring(true)}>
                        Восстановить
                      </Button>
                    ) : null}
                  </div>
                } />
              {!data.can_restore && student.is_archived ? (
                <p className="-mt-2 mb-4 text-xs text-ink-secondary">Восстановление выполняет ассистент или администратор системы.</p>
              ) : null}

              <Card title="Основная информация">
                <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <Info label="ФИО">{student.name}</Info>
                  <Info label="Контакты">{[student.phone, student.parent_phone && `родитель: ${student.parent_name
                    ? `${student.parent_name}, ` : ''}${student.parent_phone}`].filter(Boolean).join(' · ')}</Info>
                  <Info label="Последняя группа">{student.last_group?.name}</Info>
                  <Info label="Направление">{student.subjects.join(', ')}</Info>
                  <Info label="Дата поступления">{formatDate(student.enrollment_date)}</Info>
                  <Info label="Дата деактивации">{formatDate(deactivation?.date)}</Info>
                  <Info label="Причина ухода">
                    {deactivation ? `${deactivation.reason_display || 'Не указана'}${deactivation.comment ? ` — ${deactivation.comment}` : ''}` : null}
                  </Info>
                  <Info label="Кто деактивировал">
                    {deactivation ? `${deactivation.performed_by?.name ?? 'Система'} · ${formatDateTime(deactivation.created_at)}` : null}
                  </Info>
                </dl>
              </Card>

              <Card className="mt-4" title="Финансы"
                description="Деактивация не меняет долг: он остаётся до оплаты или отдельного списания в карточке договора.">
                <FinanceSummary finance={data.finance} />
              </Card>

              <div className="mt-6">
                <Tabs aria-label="Разделы карточки" items={TABS} value={tab} onChange={setTab} />
                <div className="mt-4">
                  {tab === 'payments' ? <PaymentsTable data={data} /> : null}
                  {tab === 'invoices' ? <InvoicesTable data={data} /> : null}
                  {tab === 'contracts' ? (data.contracts.length
                    ? <div className="space-y-4">{data.contracts.map((c) => <ContractBlock key={c.id} contract={c} />)}</div>
                    : <EmptyState title="Договоров не было" description="Студент обучался без договора оплаты." />) : null}
                  {tab === 'study' ? <StudyBlock data={data} /> : null}
                </div>
              </div>

              {restoring ? <RestoreModal studentId={student.id} name={student.name} onClose={() => setRestoring(false)} /> : null}
            </>
          )
        }}
      </Loadable>
    </div>
  )
}
