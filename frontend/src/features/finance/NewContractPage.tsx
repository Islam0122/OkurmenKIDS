import { useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { financeApi } from '@/api/finance'
import { newIdempotencyKey } from '@/api/accounting'
import { PageHeader } from '@/components/layout/PageHeader'
import { BackLink } from '@/components/ui/BackLink'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { Field, fieldErrors } from '@/features/worklog/formUi'
import type { PaymentMode, ReservationMode } from '@/types/finance'
import { cn } from '@/utils/cn'

import { FINANCE_KEY, som, today, useFinanceMe, useFinanceOptions, useInvalidateFinance, useRunner } from './ui'

/** Сумма в тыйынах — только для предпросмотра; считает и проверяет сервер. */
function cents(value: string | null | undefined): number {
  const n = Number(String(value ?? '').replace(',', '.').replace(/\s/g, ''))
  return Number.isFinite(n) ? Math.round(n * 100) : 0
}

const fromCents = (n: number) => (n / 100).toFixed(2)

function Choice<T extends string>({ name, value, options, onChange }: {
  name: string
  value: T
  options: { value: NoInfer<T>; label: string; hint?: string; disabled?: boolean }[]
  onChange: (v: NoInfer<T>) => void
}) {
  return (
    <div className="grid gap-2 sm:grid-cols-2" role="radiogroup" aria-label={name}>
      {options.map((o) => (
        <label key={o.value} className={cn('flex cursor-pointer gap-3 rounded-lg border p-3 text-sm',
          value === o.value ? 'border-brand-500 bg-brand-50' : 'border-border bg-surface', o.disabled && 'cursor-not-allowed opacity-50')}>
          <input type="radio" name={name} className="mt-0.5" checked={value === o.value} disabled={o.disabled}
            onChange={() => onChange(o.value)} />
          <span><span className="font-medium text-ink">{o.label}</span>
            {o.hint ? <span className="block text-xs text-ink-secondary">{o.hint}</span> : null}</span>
        </label>
      ))}
    </div>
  )
}

export function NewContractPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const me = useFinanceMe()
  const options = useFinanceOptions()
  const invalidate = useInvalidateFinance()
  const { run, busy } = useRunner()
  const key = useRef(newIdempotencyKey())
  const plans = useQuery({ queryKey: [...FINANCE_KEY, 'plans'], queryFn: financeApi.plans })
  const [studentId, setStudentId] = useState<number | null>(params.get('student') ? Number(params.get('student')) : null)
  const [studentSearch, setStudentSearch] = useState('')
  const students = useQuery({
    queryKey: [...FINANCE_KEY, 'lms-students', 'pick', studentSearch],
    queryFn: () => financeApi.lmsStudents({ search: studentSearch || undefined, registered: 'no' }),
  })
  const [planId, setPlanId] = useState<number | null>(null)
  const [startDate, setStartDate] = useState(today())
  const [parentName, setParentName] = useState('')
  const [parentPhone, setParentPhone] = useState('')
  const [mode, setMode] = useState<PaymentMode>('MONTHLY')
  const [discount, setDiscount] = useState(false)
  const [finalPrice, setFinalPrice] = useState('')
  const [reason, setReason] = useState('')
  const [reservation, setReservation] = useState('')
  const [reservationMode, setReservationMode] = useState<ReservationMode>('FIRST_MONTH')
  const [reservationReceived, setReservationReceived] = useState(false)
  const [firstPayment, setFirstPayment] = useState('')
  const [method, setMethod] = useState('cash')
  const [payer, setPayer] = useState('')
  const [specialTerms, setSpecialTerms] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})

  const activePlans = (plans.data?.results ?? []).filter((p) => p.is_active)
  const plan = activePlans.find((p) => p.id === planId) ?? null
  const student = students.data?.results.find((s) => s.id === studentId)
  const isAccountant = me.data?.can_record_payments ?? false
  const standard = plan?.current?.standard_course_price ?? plan?.current?.package_price ?? null
  const months = plan?.duration_months ?? 1

  const preview = useMemo(() => {
    const std = cents(standard)
    const fin = discount ? cents(finalPrice) : std
    const res = cents(reservation)
    const firstMonth = mode === 'FULL_PREPAY' ? fin : Math.floor(fin / months)
    const received = (reservationReceived ? res : 0) + cents(firstPayment)
    const resToFirst = reservationReceived && reservationMode === 'FIRST_MONTH' ? res : 0
    return {
      std, fin, discount: Math.max(std - fin, 0), firstMonth, res,
      firstMonthDue: Math.max(firstMonth - resToFirst - cents(firstPayment), 0),
      received, outstanding: Math.max(fin - received, 0),
    }
  }, [standard, discount, finalPrice, reservation, mode, months, reservationReceived, reservationMode, firstPayment])

  const limit = Number(me.data?.max_manager_discount_percent ?? 0)
  const overLimit = discount && !isAccountant && preview.std > 0 && preview.discount * 100 > preview.std * limit

  async function submit() {
    if (!studentId || !planId) {
      setErrors({ student: studentId ? '' : 'Выберите студента', plan: planId ? '' : 'Выберите программу' })
      return
    }
    setErrors({})
    let createdId: number | null = null
    const ok = await run(async () => {
      try {
        const contract = await financeApi.createContract({
          student: studentId, plan: planId, start_date: startDate, parent_name: parentName, parent_phone: parentPhone,
          payment_mode: mode, reservation_allocation: reservationMode, discount_enabled: discount,
          final_course_price: discount ? finalPrice : null, discount_reason: reason,
          reservation_amount: reservation || null, reservation_received: isAccountant && reservationReceived,
          initial_payment: isAccountant && firstPayment ? firstPayment : null, payment_method: method, payer_name: payer,
          special_terms: specialTerms,
        }, key.current)
        createdId = contract.id
      } catch (error) {
        setErrors(fieldErrors(error))
        throw error
      }
    }, 'Договор оформлен')
    if (ok && createdId) {
      invalidate()
      navigate(`/finance/students/${createdId}`, { replace: true })
    }
  }

  return (
    <div className="max-w-5xl">
      <BackLink to="/finance/students">Все студенты</BackLink>
      <PageHeader title="Новый договор" description="Программа, стоимость курса, скидка и бронь. Деньги при зачислении проводит бухгалтер." />
      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <div className="space-y-4">
          <Card title="Студент и программа">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Студент" required error={errors.student} className="sm:col-span-2">
                {student || (studentId && !students.data) ? (
                  <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2 text-sm">
                    <span>{student?.name ?? `Студент #${studentId}`}{student?.group_name ? ` · ${student.group_name}` : ''}</span>
                    <Button size="sm" variant="ghost" onClick={() => setStudentId(null)}>Изменить</Button>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <SearchInput value={studentSearch} onChange={setStudentSearch} placeholder="Найдите студента без договора" />
                    <div className="max-h-48 overflow-y-auto rounded-lg border border-border">
                      {(students.data?.results ?? []).slice(0, 20).map((s) => (
                        <button key={s.id} type="button" className="block w-full px-3 py-2 text-left text-sm hover:bg-surface-hover"
                          onClick={() => { setStudentId(s.id); setParentPhone(s.parent_phone) }}>
                          {s.name} <span className="text-ink-secondary">· {s.group_name ?? 'без группы'}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </Field>
              <Field label="Программа" htmlFor="nc-plan" required error={errors.plan}>
                <Select id="nc-plan" value={planId ? String(planId) : ''} placeholder="Выберите программу"
                  options={activePlans.map((p) => ({ value: String(p.id), label: p.name }))}
                  onChange={(e) => {
                    const next = activePlans.find((p) => p.id === Number(e.target.value))
                    setPlanId(next?.id ?? null)
                    if (next && !next.allow_monthly) setMode('FULL_PREPAY')
                    if (next && !next.allow_full_prepay) setMode('MONTHLY')
                  }} />
              </Field>
              <Field label="Дата начала обучения" htmlFor="nc-start">
                <Input id="nc-start" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
              </Field>
              <Field label="Родитель (ФИО)" htmlFor="nc-parent">
                <Input id="nc-parent" value={parentName} onChange={(e) => setParentName(e.target.value)} />
              </Field>
              <Field label="Телефон родителя" htmlFor="nc-phone">
                <Input id="nc-phone" value={parentPhone} onChange={(e) => setParentPhone(e.target.value)} />
              </Field>
            </div>
            {plan ? (
              <p className="mt-3 rounded-lg bg-surface-muted px-3 py-2 text-sm text-ink-secondary">
                {plan.duration_months ? `${plan.duration_months} учебных месяца(ев) × ${plan.current?.lessons_per_package} уроков ${plan.subject_name ?? ''}` : 'Без фиксированного срока'}
                {' · '}месяц {som(plan.current?.package_price)} · оплата не позднее {plan.payment_deadline_lessons}-го урока месяца
              </p>
            ) : null}
          </Card>

          <Card title="Стоимость и способ оплаты">
            <Choice name="Способ оплаты" value={mode} onChange={setMode} options={[
              { value: 'MONTHLY', label: 'Помесячная оплата', hint: 'Начисление в начале каждого учебного месяца', disabled: plan ? !plan.allow_monthly : false },
              { value: 'FULL_PREPAY', label: 'Предоплата за весь курс', hint: 'Одно начисление на всю итоговую сумму', disabled: plan ? !plan.allow_full_prepay : false },
            ]} />
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              <Field label="Стандартная стоимость курса" htmlFor="nc-standard">
                <Input id="nc-standard" value={som(standard)} readOnly aria-readonly className="bg-surface-muted" />
              </Field>
              <Field label="Итоговая стоимость курса" htmlFor="nc-final" error={errors.final_course_price}>
                <Input id="nc-final" inputMode="decimal" disabled={!discount} value={discount ? finalPrice : (standard ?? '')}
                  onChange={(e) => setFinalPrice(e.target.value)} placeholder="например 45000" />
              </Field>
              <Field label="Размер скидки в сомах" htmlFor="nc-discount">
                <Input id="nc-discount" value={som(fromCents(preview.discount))} readOnly aria-readonly className="bg-surface-muted" />
              </Field>
            </div>
            <label className="mt-3 flex items-center gap-2 text-sm font-medium text-ink">
              <input type="checkbox" checked={discount} onChange={(e) => setDiscount(e.target.checked)} />
              Скидка предоставлена
            </label>
            {discount ? (
              <Field label="Причина скидки" htmlFor="nc-reason" required className="mt-3" error={errors.discount_reason}>
                <Textarea id="nc-reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)}
                  placeholder="Например: полная предоплата, согласовано директором" />
              </Field>
            ) : null}
            {overLimit ? (
              <p className="mt-2 text-sm text-warning">Скидка больше {limit}% — договор уйдёт на согласование бухгалтеру, начисления до решения будут черновиками.</p>
            ) : null}
          </Card>

          <Card title="Бронь и деньги при зачислении">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Сумма брони" htmlFor="nc-res" help="Аванс, засчитывается в оплату обучения">
                <Input id="nc-res" inputMode="decimal" value={reservation} onChange={(e) => setReservation(e.target.value)} />
              </Field>
            </div>
            {reservation ? (
              <div className="mt-3">
                <Choice name="Учёт брони" value={reservationMode} onChange={setReservationMode} options={[
                  { value: 'FIRST_MONTH', label: 'В первый месяц', hint: 'Уменьшает доплату за месяц 1' },
                  { value: 'COURSE_TOTAL', label: 'В общую стоимость курса', hint: 'Депозит, закрывает последний месяц' },
                ]} />
              </div>
            ) : null}
            {isAccountant ? (
              <div className="mt-4 space-y-3 border-t border-border pt-4">
                {reservation ? (
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={reservationReceived} onChange={(e) => setReservationReceived(e.target.checked)} />
                    Бронь получена сейчас
                  </label>
                ) : null}
                <div className="grid gap-3 sm:grid-cols-3">
                  <Field label="Оплата сейчас (сверх брони)" htmlFor="nc-pay">
                    <Input id="nc-pay" inputMode="decimal" value={firstPayment} onChange={(e) => setFirstPayment(e.target.value)} />
                  </Field>
                  <Field label="Способ оплаты" htmlFor="nc-method">
                    <Select id="nc-method" value={method} onChange={(e) => setMethod(e.target.value)}
                      options={options.data?.payment_methods ?? [{ value: 'cash', label: 'Наличные' }]} />
                  </Field>
                  <Field label="Плательщик" htmlFor="nc-payer">
                    <Input id="nc-payer" value={payer} onChange={(e) => setPayer(e.target.value)} placeholder={parentName} />
                  </Field>
                </div>
              </div>
            ) : (
              <p className="mt-3 text-sm text-ink-secondary">Полученные деньги регистрирует бухгалтер — после оформления договора.</p>
            )}
            <Field label="Особые условия" htmlFor="nc-terms" className="mt-3">
              <Textarea id="nc-terms" rows={2} value={specialTerms} onChange={(e) => setSpecialTerms(e.target.value)} />
            </Field>
          </Card>
        </div>

        <aside className="lg:sticky lg:top-20 lg:self-start">
          <Card title="Итого по договору">
            <dl className="space-y-2 text-sm">
              <Row label="Стандартная стоимость" value={som(fromCents(preview.std))} />
              <Row label="Скидка" value={som(fromCents(preview.discount))} />
              <Row label="Итоговая стоимость" value={som(fromCents(preview.fin))} strong />
              <Row label={mode === 'FULL_PREPAY' ? 'Начисление за весь курс' : 'Первый месяц'} value={som(fromCents(preview.firstMonth))} />
              {preview.res ? <Row label="Бронь" value={som(fromCents(preview.res))} /> : null}
              <Row label="Получено сейчас" value={som(fromCents(preview.received))} />
              <Row label={mode === 'FULL_PREPAY' ? 'Осталось оплатить' : 'Доплата за первый месяц'} value={som(fromCents(preview.firstMonthDue))} strong />
              <Row label="Остаток по договору" value={som(fromCents(preview.outstanding))} />
            </dl>
            <Button className="mt-4 w-full" onClick={submit} isLoading={busy}>Оформить договор</Button>
            <p className="mt-2 text-xs text-ink-secondary">Предпросмотр. Окончательный расчёт — на сервере; бронь вычитается один раз.</p>
          </Card>
        </aside>
      </div>
    </div>
  )
}

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-ink-secondary">{label}</dt>
      <dd className={cn('tabular-nums', strong ? 'font-semibold text-ink' : 'text-ink')}>{value}</dd>
    </div>
  )
}
