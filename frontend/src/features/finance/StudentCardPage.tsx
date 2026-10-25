import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Pencil, Phone, Plus } from 'lucide-react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'

import { financeApi } from '@/api/finance'
import { newIdempotencyKey } from '@/api/accounting'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { BackLink } from '@/components/ui/BackLink'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { DataTable } from '@/components/ui/DataTable'
import { EmptyState } from '@/components/ui/EmptyState'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { ReasonModal, Section } from '@/features/accounting/shared'
import { Field } from '@/features/worklog/formUi'
import type { ContractCard, Payment, Reservation, StudyProgress } from '@/types/finance'

import { OperationsTable, ReservationBlock, ScheduleBlock } from './CardSections'

import {
  Amount,
  ContactModal,
  ContractStatusBadge,
  FINANCE_KEY,
  InvoiceStatusBadge,
  Loadable,
  Stat,
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

const MONTH_STATUS: Record<string, string> = {
  PLANNED: 'Следующий', ACTIVE: 'Текущий', COMPLETED: 'Пройден', CANCELLED: 'Отменён',
}

/** Три независимых показателя (backend `progress`): учебный месяц группы, посещаемость ученика,
 * финансовый пакет договора. Месяц группы не подтверждает посещение и не меняет начисления. */
function ProgressBlock({ progress, subject }: { progress: StudyProgress; subject: string }) {
  const g = progress.group
  const pkg = progress.package
  return (
    <div className="mt-4 grid gap-3 sm:grid-cols-3" data-testid="study-progress">
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
  const [reversing, setReversing] = useState<Payment | null>(null)
  const [reservationPay, setReservationPay] = useState<Reservation | null>(null)
  const invalidate = useInvalidateFinance()
  const { run } = useRunner()
  const canPay = me.data?.can_record_payments ?? false
  const canTerms = (me.data?.can_register ?? false) && c.is_course && (c.status === 'ACTIVE' || c.status === 'PAUSED')

  return (
    <div>
      <PageHeader
        title={c.student_name}
        badge={<div className="flex gap-1"><StageBadge stage={row.stage} /><ContractStatusBadge status={c.status} label={c.status_display} /></div>}
        description={`${c.group_name ?? 'Без группы'} · ${c.program_name ?? c.plan_name} · ${c.parent_name || 'родитель не указан'}${c.parent_phone ? ` · ${c.parent_phone}` : ''}`}
        actions={
          <div className="flex flex-wrap gap-2">
            {canPay ? <Button leftIcon={<Plus className="size-4" />} onClick={() => navigate(`/finance/payments/new?profile=${c.id}`)}>Добавить платёж</Button> : null}
            {canPay ? <Button variant="secondary" leftIcon={<Phone className="size-4" />} onClick={() => setContact(true)}>Контакт</Button> : null}
            {canTerms ? <Button variant="secondary" leftIcon={<Pencil className="size-4" />} onClick={() => setTerms(true)}>Стоимость курса</Button> : null}
          </div>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="К оплате сейчас" value={som(summary.due_now)} tone={summary.overdue !== '0.00' ? 'danger' : undefined}
          hint={summary.overdue !== '0.00' ? `из них просрочено ${som(summary.overdue)}` : 'наступившие начисления'} />
        <Stat label="Получено по договору" value={som(summary.net_received)}
          hint={`оплачено по начислениям ${som(summary.allocated)}${summary.refunded !== '0.00' ? `, возвраты ${som(summary.refunded)}` : ''}${summary.voided_count ? `; сторно ${som(summary.voided)} не учитывается` : ''}`} />
        <Stat label="Свободный аванс" value={som(summary.credit)}
          hint={summary.credit_reserved_future !== '0.00'
            ? `из них на будущие начисления (прогноз) ${som(summary.credit_reserved_future)}`
            : summary.reservation_unused !== '0.00' ? `в т.ч. бронь ${som(summary.reservation_unused)}` : 'получено, но не распределено'} />
        <Stat label="Осталось оплатить" value={som(summary.net_to_pay)} tone="brand"
          hint={summary.course_paid_in_full ? 'курс полностью оплачен'
            : summary.future && summary.future !== '0.00' ? `будущие начисления ${som(summary.future)}` : undefined} />
      </div>
      {summary.course_paid_in_full ? (
        <p className="mt-3 rounded-xl border border-border bg-brand-50 p-3 text-sm text-brand-700" data-testid="course-paid">
          <b>Курс полностью оплачен</b>{c.final_course_price ? ` — ${som(c.final_course_price)}` : ''}. Текущий долг 0 сом, просрочки нет,
          дополнительные платежи не требуются. Добровольно внесённая сумма будет учтена как аванс.
        </p>
      ) : null}
      <p className="mt-2 text-xs text-ink-secondary" data-testid="money-breakdown">
        Получено {som(summary.net_received)} = оплачено по начислениям {som(summary.allocated)} + свободный аванс {som(summary.credit)}
        {summary.credit !== '0.00' ? ` (на текущий долг ${som(summary.credit_unapplied)}, на будущие начисления — прогноз ${som(summary.credit_reserved_future)}, сверх договора ${som(summary.credit_unreserved)})` : ''}.
        {' '}Текущий долг {som(summary.due_now)} · будущие начисления {som(summary.future ?? '0')} · осталось оплатить {som(summary.net_to_pay)}.
        {summary.voided_count ? ` Сторнировано ${summary.voided_count} платеж(а) на ${som(summary.voided)} — это отмена записи, не возврат денег.` : ''}
      </p>

      {summary.credit_unapplied !== '0.00' ? (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-warning/20 bg-warning-soft p-3 text-sm text-warning">
          <span>
            Свободный аванс {som(summary.credit_unapplied)} не распределён на неоплаченные начисления ({som(summary.invoices_balance)}).
            «К оплате сейчас» уже учитывает этот аванс; распределите его, чтобы начисления получили статус «Оплачено».
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

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title="Условия договора">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <Term label="Стандартная стоимость курса" value={som(c.standard_course_price)} />
            <Term label="Итоговая стоимость курса" value={som(c.final_course_price)} />
            <Term label="Скидка" value={c.discount_enabled ? som(c.discount_amount) : 'нет'} />
            <Term label="Причина скидки" value={c.discount_reason || '—'} />
            <Term label="Способ оплаты" value={c.payment_mode_display} />
            <Term label="Учёт брони" value={c.reservation_allocation_display} />
            <Term label="Учебный месяц" value={c.lessons_per_month ? `${c.lessons_per_month} уроков ${c.subject_name ?? ''} · ${som(c.month_price)}` : '—'} />
            <Term label="Срок оплаты" value={c.deadline_lessons ? `не позднее ${c.deadline_lessons}-го урока месяца` : '—'} />
            <Term label="Начало обучения" value={formatDate(c.start_date)} />
            <Term label="Месяцев в курсе" value={c.duration_months ? String(c.duration_months) : 'без срока'} />
          </dl>
          {c.special_terms ? <p className="mt-3 text-sm text-ink-secondary">Особые условия: {c.special_terms}</p> : null}
        </Card>
        <Card title="Бронь">
          <ReservationBlock reservations={card.reservations} canPay={canPay} onPay={setReservationPay} />
        </Card>
      </div>

      <LessonCount profile={c.id} canFix={me.data?.can_manage_settings ?? false} />

      {card.progress ? <ProgressBlock progress={card.progress} subject={c.subject_name ?? 'IT'} /> : null}

      <Section title={c.is_course ? 'Финансовые пакеты договора (по ним начисления)' : 'Учебные месяцы'}>
        {card.months.length === 0 ? <EmptyState title="Месяцев пока нет" /> : (
          <DataTable rows={card.months} getRowKey={(m) => m.id} columns={[
            { key: 'n', header: c.is_course ? 'Пакет' : 'Месяц', render: (m) => <span className="font-medium">№{m.month_number ?? m.number}</span> },
            { key: 'st', header: 'Статус', render: (m) => <Badge tone={m.status === 'ACTIVE' ? 'info' : m.status === 'COMPLETED' ? 'success' : 'muted'}>{MONTH_STATUS[m.status]}</Badge> },
            { key: 'l', header: 'Уроки IT', render: (m) => `${m.lessons_used} из ${m.lessons_total}` },
            { key: 'inv', header: 'Начисление', render: (m) => m.invoice ? <Amount value={m.invoice.amount} />
              : m.course_share ? (
                <span className="text-sm" title={`Доля начисления «Весь курс» ${m.course_share.number}, не отдельное начисление`}>
                  <Amount value={m.course_share.amount} />
                  <span className="block text-xs text-ink-secondary">
                    {m.course_share.paid_in_full ? 'оплачен предоплатой курса' : `доля курса, оплачено ${som(m.course_share.paid)}`}
                  </span>
                </span>
              ) : <span className="text-sm text-ink-secondary">оплачен по договору</span> },
            { key: 'bal', header: 'Остаток', render: (m) => m.invoice ? <Amount value={m.invoice.balance} /> : '—' },
            { key: 'dates', header: 'Начат / завершён', render: (m) => `${formatDate(m.started_on)} — ${formatDate(m.completed_on)}` },
          ]} />
        )}
      </Section>

      {card.schedule ? (
        <Section title="График оплаты по договору">
          <ScheduleBlock schedule={card.schedule} profile={c.id} canEdit={me.data?.can_manage_settings ?? false} />
        </Section>
      ) : null}

      <Section title="Начисления">
        {card.invoices.length === 0 ? <EmptyState title="Начислений нет" /> : (
          <DataTable rows={card.invoices} getRowKey={(i) => i.id} columns={[
            { key: 'num', header: 'Номер', render: (i) => <span className="font-medium">{i.number}</span> },
            { key: 'what', header: 'За что', render: (i) => i.kind === 'COURSE' ? 'Весь курс' : `Месяц №${i.month_number ?? i.package_number}` },
            { key: 'amount', header: 'Сумма', render: (i) => <Amount value={i.amount} /> },
            { key: 'paid', header: 'Оплачено', render: (i) => <Amount value={i.amount_paid} tone="muted" /> },
            { key: 'bal', header: 'Остаток', render: (i) => <Amount value={i.balance} tone={i.status === 'OVERDUE' ? 'danger' : undefined} /> },
            { key: 'due', header: 'Срок', render: (i) => i.due_lesson ? `${i.due_lesson}-й урок (сейчас ${i.lessons_used})` : formatDate(i.due_date) },
            { key: 'st', header: 'Статус', render: (i) => <div className="flex flex-wrap gap-1"><InvoiceStatusBadge status={i.status} label={i.status_display} />
              {i.stage === 'deadline' ? <StageBadge stage="deadline" /> : null}</div> },
          ]} />
        )}
      </Section>

      {card.payments ? (
        <Section title="Платежи и чеки">
          <div id="payments" />
          {card.payments.length === 0 ? <EmptyState title="Платежей пока нет" /> : (
            <OperationsTable payments={card.payments} canPay={canPay} onReverse={setReversing} />
          )}
        </Section>
      ) : null}

      {card.contacts ? (
        <Section title="Контакты с родителями">
          {card.contacts.length === 0 ? <p className="text-sm text-ink-secondary">Контактов не было.</p> : (
            <ul className="space-y-2">
              {card.contacts.map((x) => (
                <li key={x.id} className="card p-3 text-sm">
                  <p className="font-medium">{formatDateTime(x.contacted_at)} · {x.channel_display} · {x.result_display}</p>
                  <p className="text-ink-secondary">{x.staff_name}{x.comment ? ` — ${x.comment}` : ''}
                    {x.promised_payment_date ? ` · обещал оплатить ${formatDate(x.promised_payment_date)}` : ''}</p>
                </li>
              ))}
            </ul>
          )}
        </Section>
      ) : null}

      {contact ? <ContactModal profile={c.id} student={c.student_name} onClose={() => setContact(false)} /> : null}
      {terms ? <TermsModal card={card} onClose={() => setTerms(false)} /> : null}
      {reservationPay ? <ReservationPayModal reservation={reservationPay} onClose={() => setReservationPay(null)} /> : null}
      <ReasonModal isOpen={reversing !== null} title="Сторно платежа" tone="danger" confirmLabel="Сторнировать"
        description="Платёж не удаляется: он помечается отменённым, распределения возвращаются, чек аннулируется. Операция попадёт в журнал."
        onClose={() => setReversing(null)}
        onConfirm={async (reason) => {
          const ok = await run(() => financeApi.reversePayment(reversing!.id, reason), 'Платёж сторнирован')
          if (ok) invalidate()
          return ok
        }} />
    </div>
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
  return (
    <Modal isOpen onClose={onClose} title="Итоговая стоимость курса">
      <p className="mb-3 text-sm text-ink-secondary">Новая цена действует на будущие учебные месяцы. Уже выставленные начисления не меняются.
        Стандартная стоимость — {som(c.standard_course_price)}.</p>
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
        <div className="mt-3 overflow-x-auto">
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
