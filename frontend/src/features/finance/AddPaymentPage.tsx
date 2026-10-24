import { useEffect, useRef, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { CheckCircle2, Download, Plus, Printer, UserRound } from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { financeApi } from '@/api/finance'
import { newIdempotencyKey } from '@/api/accounting'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { Field, fieldErrors } from '@/features/worklog/formUi'
import type { Payment, PaymentTarget, QueueRow } from '@/types/finance'
import { cn } from '@/utils/cn'

import { periodMonth, useFinancePeriod } from './period'
import { FINANCE_KEY, Loadable, StageBadge, som, today, useFinanceOptions, useInvalidateFinance, useRunner } from './ui'

/** 1. студент → 2. договор и долг → 3. назначение → 4–7. сумма, способ, дата
 * → предпросмотр → 8. сохранить → 9. распределение на сервере → 10. чек. */
export function AddPaymentPage() {
  const [params, setParams] = useSearchParams()
  const profile = params.get('profile') ? Number(params.get('profile')) : null
  const [saved, setSaved] = useState<Payment | null>(null)

  if (saved) {
    return <Saved payment={saved} onNext={() => { setSaved(null); setParams({}) }} />
  }
  return (
    <div className="max-w-5xl">
      <PageHeader title="Добавить платёж" description="Найдите студента, проверьте долг, выберите назначение и сохраните — чек сразу готов к печати." />
      {profile ? <PaymentForm key={profile} profile={profile} initialInvoice={params.get('invoice')}
        onChange={() => setParams({})} onSaved={setSaved} /> : <StudentPicker onPick={(p) => setParams({ profile: String(p) })} />}
    </div>
  )
}

function StudentPicker({ onPick }: { onPick: (profile: number) => void }) {
  const [search, setSearch] = useState('')
  const options = useFinanceOptions()
  const [group, setGroup] = useState('')
  const query = useQuery({
    queryKey: [...FINANCE_KEY, 'queue', 'all', 'pick', search, group],
    queryFn: () => financeApi.queue('all', { search: search || undefined, group: group ? Number(group) : undefined, page_size: 20 }),
    placeholderData: keepPreviousData,
  })
  return (
    <Card title="1. Студент">
      <div className="grid gap-3 sm:grid-cols-[1fr_220px]">
        <SearchInput value={search} onChange={setSearch} placeholder="Имя, телефон родителя или группа" />
        <Select aria-label="Группа" value={group} placeholder="Все группы" onChange={(e) => setGroup(e.target.value)}
          options={(options.data?.groups ?? []).map((g) => ({ value: String(g.id), label: g.name }))} />
      </div>
      <div className="mt-3 divide-y divide-border rounded-lg border border-border">
        <Loadable query={query} empty={(d) => d.count === 0} emptyTitle="Никого не нашли">
          {(data) => (
            <>
              {data.results.map((r) => (
                <button key={r.profile} type="button" onClick={() => onPick(r.profile)}
                  className="flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left hover:bg-surface-hover">
                  <span>
                    <span className="font-medium text-ink">{r.student_name}</span>
                    <span className="block text-xs text-ink-secondary">{r.group_name ?? 'без группы'} · {r.program ?? r.plan_name} · {r.parent_phone}</span>
                  </span>
                  <span className="text-right text-sm">
                    <span className={cn('block tabular-nums', r.overdue_amount !== '0.00' && 'font-semibold text-danger')}>{som(r.due_now)}</span>
                    <span className="text-xs text-ink-secondary">к оплате</span>
                  </span>
                </button>
              ))}
            </>
          )}
        </Loadable>
      </div>
    </Card>
  )
}

function PaymentForm({ profile, initialInvoice, onChange, onSaved }: {
  profile: number
  initialInvoice: string | null
  onChange: () => void
  onSaved: (p: Payment) => void
}) {
  const options = useFinanceOptions()
  const invalidate = useInvalidateFinance()
  const { run, busy } = useRunner()
  // Один ключ на открытую форму: двойной клик или повторная отправка вернут тот же платёж.
  const key = useRef(newIdempotencyKey())
  const submitted = useRef(false)
  const card = useQuery({ queryKey: [...FINANCE_KEY, 'card', profile], queryFn: () => financeApi.card(profile) })
  const unpaid = (card.data?.invoices ?? []).filter((i) => ['OPEN', 'PARTIALLY_PAID', 'OVERDUE'].includes(i.status))
  const [mode, setMode] = useState<PaymentTarget>(initialInvoice ? 'invoice' : 'auto')
  const [invoice, setInvoice] = useState<string>(initialInvoice ?? '')
  const [amount, setAmount] = useState('')
  const [method, setMethod] = useState('cash')
  // Дата фактического получения денег: по умолчанию сегодня, можно прошлую
  // (платёж, полученный в сентябре, вносится в октябре сентябрём).
  const period = useFinancePeriod()
  const [date, setDate] = useState(today())
  const [reference, setReference] = useState('')
  const [payer, setPayer] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [debounced, setDebounced] = useState('')

  useEffect(() => {
    const t = setTimeout(() => setDebounced(amount), 300)
    return () => clearTimeout(t)
  }, [amount])
  useEffect(() => {
    if (card.data && !payer) setPayer(card.data.contract.parent_name)
    if (card.data && !amount) {
      const target = mode === 'invoice' ? unpaid.find((i) => String(i.id) === invoice) : null
      const suggested = target?.balance ?? card.data.summary.due_now
      if (suggested && suggested !== '0.00') setAmount(suggested)
    }
    // Подставляем один раз при загрузке карточки.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [card.data])

  const validAmount = /^\d+([.,]\d{1,2})?$/.test(debounced) && Number(debounced.replace(',', '.')) > 0
  const preview = useQuery({
    queryKey: [...FINANCE_KEY, 'preview', profile, debounced, mode, invoice],
    queryFn: () => financeApi.previewPayment({ profile, amount: debounced.replace(',', '.'), mode,
      invoice: mode === 'invoice' && invoice ? Number(invoice) : null }),
    enabled: validAmount && (mode !== 'invoice' || !!invoice),
    placeholderData: keepPreviousData,
  })

  async function save() {
    if (submitted.current) return
    if (!confirmed) {
      setErrors({ confirmed: 'Подтвердите, что деньги получены' })
      return
    }
    submitted.current = true
    let result: Payment | null = null
    const ok = await run(async () => {
      try {
        result = await financeApi.recordPayment({
          profile, amount: amount.replace(',', '.'), received_date: date, method, mode,
          purpose: mode === 'advance' ? 'prepayment' : 'tuition',
          invoice: mode === 'invoice' && invoice ? Number(invoice) : null, reference, payer_name: payer,
        }, key.current)
      } catch (error) {
        setErrors(fieldErrors(error))
        throw error
      }
    }, 'Платёж сохранён')
    if (ok && result) {
      invalidate()
      onSaved(result)
    } else {
      submitted.current = false
    }
  }

  return (
    <Loadable query={card}>
      {(data) => {
        const row: QueueRow = data.row
        const p = preview.data
        return (
          <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
            <div className="space-y-4">
              <Card title="2. Договор и задолженность" actions={<Button size="sm" variant="ghost" onClick={onChange}>Другой студент</Button>}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-lg font-semibold text-ink">{row.student_name}</p>
                    <p className="text-sm text-ink-secondary">{row.group_name ?? 'без группы'} · {row.program ?? row.plan_name} · {data.contract.payment_mode_display}</p>
                    <p className="mt-1 text-sm text-ink-secondary">
                      Курс {som(data.contract.final_course_price)}{data.contract.discount_enabled ? ` (скидка ${som(data.contract.discount_amount)})` : ''}
                      {row.month_number ? ` · месяц ${row.month_number}${row.duration_months ? ` из ${row.duration_months}` : ''}, IT ${row.lessons_used} из ${row.lessons_total}` : ''}
                    </p>
                  </div>
                  <StageBadge stage={row.stage} />
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
                  <Mini label="К оплате сейчас" value={som(data.summary.due_now)} />
                  <Mini label="Просрочено" value={som(data.summary.overdue)} danger={data.summary.overdue !== '0.00'} />
                  <Mini label="Аванс" value={som(data.summary.credit)} />
                  <Mini label="Остаток по договору" value={som(data.summary.outstanding)} />
                </div>
              </Card>

              <Card title="3. Назначение платежа">
                <div className="grid gap-2 sm:grid-cols-3" role="radiogroup" aria-label="Назначение платежа">
                  {([
                    ['auto', 'Текущий долг', 'Начисления по порядку, остаток — аванс'],
                    ['invoice', 'Конкретное начисление', 'Остаток — аванс'],
                    ['advance', 'Предоплата / аванс', 'Закроет будущие месяцы'],
                  ] as const).map(([value, label, hint]) => (
                    <label key={value} className={cn('flex cursor-pointer gap-2 rounded-lg border p-3 text-sm',
                      mode === value ? 'border-brand-500 bg-brand-50' : 'border-border')}>
                      <input type="radio" name="target" checked={mode === value} onChange={() => setMode(value)} className="mt-0.5" />
                      <span><span className="font-medium">{label}</span><span className="block text-xs text-ink-secondary">{hint}</span></span>
                    </label>
                  ))}
                </div>
                {mode === 'invoice' ? (
                  <Field label="Начисление" htmlFor="ap-invoice" className="mt-3" error={errors.invoice}>
                    <Select id="ap-invoice" value={invoice} placeholder="Выберите начисление" onChange={(e) => setInvoice(e.target.value)}
                      options={unpaid.map((i) => ({ value: String(i.id),
                        label: `${i.kind === 'COURSE' ? 'Весь курс' : `Месяц №${i.month_number ?? i.package_number}`} (период: ${periodMonth(i.period_date)}) — ${i.number}: начислено ${som(i.amount)}, остаток ${som(i.balance)}` }))} />
                  </Field>
                ) : null}
              </Card>

              <Card title="4–7. Сумма и подтверждение">
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Получено, сом" htmlFor="ap-amount" required error={errors.amount}>
                    <Input id="ap-amount" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} className="text-lg font-semibold" />
                  </Field>
                  <Field label="Способ оплаты" htmlFor="ap-method">
                    <Select id="ap-method" value={method} onChange={(e) => setMethod(e.target.value)}
                      options={options.data?.payment_methods ?? [{ value: 'cash', label: 'Наличные' }]} />
                  </Field>
                  <Field label="Дата фактического получения" htmlFor="ap-date" error={errors.received_date}>
                    <Input id="ap-date" type="date" max={today()} value={date} onChange={(e) => setDate(e.target.value)} />
                    <p className="mt-1 text-xs text-ink-secondary">
                      Поступление за {date ? periodMonth(date) : '—'}; время внесения записи сохранится отдельно.
                      {period.isPast && date > period.date_to ? (
                        <button type="button" className="ml-1 text-brand-700 hover:underline"
                          onClick={() => setDate(period.date_to)}>Получено в периоде «{period.label}»?</button>
                      ) : null}
                    </p>
                  </Field>
                  <Field label="Плательщик (ФИО)" htmlFor="ap-payer">
                    <Input id="ap-payer" value={payer} onChange={(e) => setPayer(e.target.value)} />
                  </Field>
                  <Field label="Номер документа / транзакции" htmlFor="ap-ref" error={errors.reference} className="sm:col-span-2">
                    <Input id="ap-ref" value={reference} onChange={(e) => setReference(e.target.value)} placeholder="для перевода или карты" />
                  </Field>
                </div>
                <label className="mt-3 flex items-center gap-2 text-sm font-medium">
                  <input type="checkbox" checked={confirmed} onChange={(e) => { setConfirmed(e.target.checked); setErrors({}) }} />
                  Деньги фактически получены
                </label>
                {errors.confirmed ? <p className="mt-1 text-sm text-danger">{errors.confirmed}</p> : null}
                {errors.detail ? <p className="mt-2 text-sm text-danger">{errors.detail}</p> : null}
              </Card>
            </div>

            <aside className="lg:sticky lg:top-20 lg:self-start">
              <Card title="До сохранения">
                {!validAmount ? <p className="text-sm text-ink-secondary">Введите сумму, чтобы увидеть результат.</p> : p ? (
                  <dl className="space-y-2 text-sm">
                    <Line label="Сумма обязательства" value={som(p.obligation)} />
                    <Line label="Уже оплачено" value={som(p.paid_before)} />
                    <Line label="Новый платёж" value={som(p.amount)} strong />
                    <Line label="Остаток после платежа" value={som(mode === 'advance' ? p.due_now_after : p.obligation_balance_after)} strong />
                    <Line label="Свободный аванс после" value={som(p.credit_after)} />
                    <Line label="Остаток по договору после" value={som(p.outstanding_after)} />
                    {p.allocations.length ? (
                      <div className="border-t border-border pt-2 text-xs text-ink-secondary">
                        <p className="mb-1">Поступление: {periodMonth(date)}. Гасит начисления:</p>
                        {p.allocations.map((a) => {
                          const inv = unpaid.find((i) => i.id === a.invoice)
                          return <p key={a.invoice}>{a.month_number ? `Месяц №${a.month_number}` : a.number}
                            {inv ? ` (за ${periodMonth(inv.period_date)})` : ''}: {som(a.payment)}</p>
                        })}
                        {p.to_credit !== '0.00' ? <p>В аванс: {som(p.to_credit)}</p> : null}
                      </div>
                    ) : null}
                  </dl>
                ) : <p className="text-sm text-ink-secondary">Считаем…</p>}
                <Button className="mt-4 w-full" size="lg" onClick={save} isLoading={busy} disabled={busy || !validAmount}>
                  Сохранить платёж
                </Button>
              </Card>
            </aside>
          </div>
        )
      }}
    </Loadable>
  )
}

function Mini({ label, value, danger }: { label: string; value: string; danger?: boolean }) {
  return (
    <div className="rounded-lg bg-surface-muted p-2">
      <p className="text-xs text-ink-secondary">{label}</p>
      <p className={cn('font-semibold tabular-nums', danger && 'text-danger')}>{value}</p>
    </div>
  )
}

function Line({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-ink-secondary">{label}</dt>
      <dd className={cn('tabular-nums', strong && 'font-semibold')}>{value}</dd>
    </div>
  )
}

function Saved({ payment, onNext }: { payment: Payment; onNext: () => void }) {
  const navigate = useNavigate()
  const { run } = useRunner()
  const receipt = payment.receipt
  return (
    <div className="mx-auto max-w-xl">
      <Card>
        <div className="text-center">
          <CheckCircle2 className="mx-auto size-12 text-brand-500" aria-hidden />
          <h1 className="mt-3 text-xl font-semibold text-ink">Платёж сохранён</h1>
          <p className="mt-1 text-ink-secondary">{payment.student_name} · {som(payment.amount)} · {payment.method_display}</p>
          {receipt ? <p className="mt-1 text-sm text-ink-secondary">Чек № {receipt.number}</p> : null}
        </div>
        <div className="mt-6 grid gap-2 sm:grid-cols-2">
          {receipt ? (
            <>
              <Button leftIcon={<Printer className="size-4" />} onClick={() => navigate(`/finance/receipts/${receipt.id}?print=1`)}>Печать чека</Button>
              <Button variant="secondary" leftIcon={<Download className="size-4" />}
                onClick={() => run(() => financeApi.downloadReceiptPdf(receipt.id))}>Скачать PDF</Button>
            </>
          ) : null}
          <Button variant="secondary" leftIcon={<Plus className="size-4" />} onClick={onNext}>Добавить следующий платёж</Button>
          <Button variant="ghost" leftIcon={<UserRound className="size-4" />} onClick={() => navigate(`/finance/students/${payment.billing_profile}`)}>
            Открыть карточку студента
          </Button>
        </div>
      </Card>
    </div>
  )
}
