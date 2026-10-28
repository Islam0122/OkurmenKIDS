import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AxiosError } from 'axios'
import { AlertTriangle, Lock } from 'lucide-react'

import { financeApi } from '@/api/finance'
import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Drawer } from '@/components/ui/Drawer'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Textarea } from '@/components/ui/Textarea'
import { Field } from '@/features/worklog/formUi'
import { extractErrorMessage } from '@/lib/apiError'
import type { CourseEditState, MonthEditBody, MonthEditResult, MonthUiStatus, ScheduleMonth } from '@/types/finance'
import { cn } from '@/utils/cn'

import { FINANCE_KEY, formatDate, formatDateTime, som, useInvalidateFinance } from './ui'

const UI_TONE: Record<MonthUiStatus, BadgeTone> = {
  future: 'muted', draft: 'muted', awaiting: 'info', partial: 'warning', paid: 'success', overdue: 'danger',
}
export const UI_LABEL: Record<MonthUiStatus, string> = {
  future: 'Будет выставлен', draft: 'Черновик', awaiting: 'Ожидает оплаты', partial: 'Частично оплачен',
  paid: 'Оплачен', overdue: 'Просрочен',
}

/** Статус месяца — всегда текстом, цвет только подсказывает. */
export function MonthStatusBadge({ status }: { status: MonthUiStatus }) {
  return <Badge tone={UI_TONE[status]}>{UI_LABEL[status]}</Badge>
}

const toNumber = (v: string | null | undefined) => (v === null || v === undefined || v === '' ? null : Number(v))
const clean = (v: string) => v.trim().replace(/\s/g, '').replace(',', '.')

const COURSE_ROWS: { key: keyof CourseEditState; label: string }[] = [
  { key: 'final_course_price', label: 'Итоговая стоимость курса' },
  { key: 'plan_total', label: 'Сумма плана месяцев' },
  { key: 'standard_course_price', label: 'Стандартная стоимость курса' },
  { key: 'discount_amount', label: 'Скидка' },
  { key: 'invoiced', label: 'Выставлено начислений' },
  { key: 'due_now', label: 'Текущий долг' },
  { key: 'overdue', label: 'Из него просрочено' },
  { key: 'future', label: 'Будущие начисления' },
  { key: 'net_to_pay', label: 'Осталось оплатить' },
  { key: 'credit', label: 'Свободный аванс' },
]

function diff(before: string | null | undefined, after: string | null | undefined): string {
  const d = (toNumber(after) ?? 0) - (toNumber(before) ?? 0)
  return `${d > 0 ? '+' : ''}${som(d.toFixed(2))}`
}

/** Изменить суммы одного учебного месяца: что можно менять — поля ввода, остальное — только чтение.
 * Последствия считает backend той же операцией с откатом (`dry_run`), сохранение — с версией графика. */
export function MonthEditDrawer({ profile, month, version, onClose }: {
  profile: number
  month: ScheduleMonth
  version?: string
  onClose: () => void
}) {
  const invalidate = useInvalidateFinance()
  const editable = month.editable ?? { standard: false, plan: false, charge: false, blocked: 'Обновите карточку.' }
  const initial = {
    standard: month.standard ?? month.standard_price ?? '',
    plan: month.plan ?? month.plan_amount ?? month.amount,
    charge: month.charge ?? '',
  }
  const [standard, setStandard] = useState(initial.standard)
  const [plan, setPlan] = useState(initial.plan)
  const [charge, setCharge] = useState(initial.charge)
  const [difference, setDifference] = useState<'course' | 'future'>('course')
  const [reason, setReason] = useState('')
  const [preview, setPreview] = useState<MonthEditResult | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<{ message: string; stale: boolean } | null>(null)
  const [busy, setBusy] = useState(false)
  const request = useRef(0)

  const changed = {
    standard: editable.standard && clean(standard) !== '' && toNumber(clean(standard)) !== toNumber(initial.standard),
    plan: editable.plan && clean(plan) !== '' && toNumber(clean(plan)) !== toNumber(initial.plan),
    charge: editable.charge && clean(charge) !== '' && toNumber(clean(charge)) !== toNumber(initial.charge),
  }
  const anyChange = changed.standard || changed.plan || changed.charge
  const moneyChange = changed.plan || changed.charge
  const body = (dry: boolean): MonthEditBody => ({
    month_number: month.month_number,
    standard_price: changed.standard ? clean(standard) : null,
    plan_amount: changed.plan ? clean(plan) : null,
    charge: changed.charge ? clean(charge) : null,
    difference, reason: reason.trim(), version, dry_run: dry,
  })
  const key = JSON.stringify({ ...body(true), reason: '' })  // причина не меняет расчёт

  useEffect(() => {
    setSaveError(null)
    if (!anyChange) {
      setPreview(null)
      setPreviewError(null)
      return
    }
    const id = ++request.current
    const timer = setTimeout(async () => {
      try {
        const result = await financeApi.editMonth(profile, body(true))
        if (id === request.current) { setPreview(result); setPreviewError(null) }
      } catch (error) {
        if (id === request.current) { setPreview(null); setPreviewError(extractErrorMessage(error)) }
      }
    }, 350)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, anyChange])

  async function save() {
    setBusy(true)
    setSaveError(null)
    try {
      await financeApi.editMonth(profile, body(false))
      invalidate()
      onClose()
    } catch (error) {
      setSaveError({ message: extractErrorMessage(error),
        stale: error instanceof AxiosError && error.response?.status === 409 })
    } finally {
      setBusy(false)
    }
  }

  const status = month.ui_status ?? 'future'
  const issued = month.state === 'invoiced'
  const courseChanges = preview ? COURSE_ROWS.filter((r) => preview.course.before[r.key] !== preview.course.after[r.key]) : []

  return (
    <Drawer isOpen onClose={onClose} side="right" size="lg" title={`Месяц №${month.month_number}: изменить суммы`}>
      <div className="space-y-4 text-sm">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 rounded-xl border border-border bg-surface-muted p-3">
          <dt className="text-ink-secondary">Начисление</dt>
          <dd className="font-medium">{month.number ?? 'ещё не выставлено'}</dd>
          <dt className="text-ink-secondary">Статус</dt>
          <dd><MonthStatusBadge status={status} /></dd>
          <dt className="text-ink-secondary">Оплачено</dt>
          <dd className="tabular-nums">{som(month.allocated ?? month.paid)}</dd>
          <dt className="text-ink-secondary">Остаток</dt>
          <dd className="tabular-nums">{issued ? som(month.balance) : '—'}</dd>
          <dt className="text-ink-secondary">Срок оплаты</dt>
          <dd>{issued ? (month.due_lesson ? `${month.due_lesson}-й урок месяца (сейчас ${month.lessons_used ?? 0})` : formatDate(month.due_date))
            : 'по плану, при выставлении'}</dd>
          {month.adjusted && month.adjusted !== '0.00' ? (
            <><dt className="text-ink-secondary">Корректировки</dt><dd className="tabular-nums">{som(month.adjusted)}</dd></>
          ) : null}
        </dl>

        {editable.blocked ? (
          <p className="flex gap-2 rounded-lg bg-warning-soft p-3 text-warning"><Lock className="mt-0.5 size-4" aria-hidden />{editable.blocked}</p>
        ) : null}

        <div className="grid gap-3 sm:grid-cols-3">
          <MoneyField id="me-standard" label="Стандарт" value={standard} onChange={setStandard} disabled={!editable.standard}
            help="Базовая цена месяца до скидок. План и начисление не меняет." />
          <MoneyField id="me-plan" label="По плану" value={plan} onChange={setPlan} disabled={!editable.plan}
            help={editable.plan ? 'Из этой суммы месяц будет начислен.' : issued
              ? 'Месяц выставлен: план равен начислению.' : 'Только чтение.'} />
          <MoneyField id="me-charge" label="Начисление" value={charge} onChange={setCharge} disabled={!editable.charge}
            help={editable.charge ? `Не меньше оплаченного: ${som(month.allocated ?? '0')}.` : 'Месяц ещё не выставлен.'} />
        </div>
        {month.plan_mismatch ? (
          <p className="rounded-lg bg-warning-soft p-2 text-warning">Сохранённый план этого месяца расходится с начислением —
            при сохранении план будет приведён к начислению.</p>
        ) : null}

        {moneyChange ? (
          <fieldset className="space-y-1">
            <legend className="mb-1 font-medium">Как учесть разницу</legend>
            <label className="flex items-start gap-2">
              <input type="radio" name="me-diff" className="mt-1" checked={difference === 'course'} onChange={() => setDifference('course')} />
              <span>Изменить стоимость курса на ту же сумму</span>
            </label>
            <label className="flex items-start gap-2">
              <input type="radio" name="me-diff" className="mt-1" checked={difference === 'future'} onChange={() => setDifference('future')} />
              <span>Стоимость курса не менять — перераспределить разницу на будущие невыставленные месяцы</span>
            </label>
          </fieldset>
        ) : null}

        <Field label="Причина корректировки" htmlFor="me-reason" required>
          <Textarea id="me-reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)}
            placeholder="Например: ошибка расчёта первого месяца" />
        </Field>

        <section aria-live="polite" aria-label="Предварительный расчёт" className="space-y-2">
          {!anyChange ? <p className="text-ink-secondary">Измените сумму — здесь появятся последствия до сохранения.</p> : null}
          {previewError ? <p role="alert" className="rounded-lg bg-danger-soft p-2 text-danger">{previewError}</p> : null}
          {anyChange && !preview && !previewError ? <p className="text-ink-secondary">Расчёт…</p> : null}
          {preview ? (
            <div className="space-y-3 rounded-xl border border-border p-3" data-testid="month-edit-preview">
              <h3 className="font-semibold">Предварительный расчёт</h3>
              <table className="w-full text-left text-sm">
                <thead className="text-xs text-ink-secondary">
                  <tr><th className="py-1">Показатель</th><th className="text-right">Было</th><th className="text-right">Станет</th><th className="text-right">Разница</th></tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {([['standard', 'Стандарт'], ['plan', 'По плану'], ['charge', 'Начисление'], ['balance', 'Остаток месяца']] as const)
                    .filter(([k]) => preview.month.before[k] !== preview.month.after[k])
                    .map(([k, label]) => <DiffRow key={k} label={`Месяц №${month.month_number}: ${label.toLowerCase()}`}
                      before={preview.month.before[k]} after={preview.month.after[k]} />)}
                  {preview.month.before.status !== preview.month.after.status ? (
                    <tr><td className="py-1">Статус месяца</td><td className="text-right">{UI_LABEL[preview.month.before.status]}</td>
                      <td className="text-right">{UI_LABEL[preview.month.after.status]}</td><td /></tr>
                  ) : null}
                  {courseChanges.map((r) => <DiffRow key={r.key} label={r.label} before={preview.course.before[r.key]}
                    after={preview.course.after[r.key]} />)}
                  {preview.other_months.map((m) => <DiffRow key={m.month_number} label={`Месяц №${m.month_number}: по плану`}
                    before={m.plan_before} after={m.plan_after} />)}
                </tbody>
              </table>
              {courseChanges.length === 0 ? <p className="text-ink-secondary">Долг, будущие начисления и остаток курса не меняются.</p> : null}
              {preview.warnings.length ? (
                <ul className="space-y-1">
                  {preview.warnings.map((w) => (
                    <li key={w} className="flex gap-2 text-warning"><AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />{w}</li>
                  ))}
                </ul>
              ) : null}
              <p className="text-xs text-ink-secondary">Платежи, чеки и поступления не меняются. Изменение будет записано в историю.</p>
            </div>
          ) : null}
        </section>

        {saveError ? (
          <div role="alert" className="rounded-lg bg-danger-soft p-3 text-danger">
            <p>Изменения не сохранены: {saveError.message}</p>
            {saveError.stale ? <Button size="sm" variant="secondary" className="mt-2" onClick={() => { invalidate(); onClose() }}>
              Обновить данные</Button> : null}
          </div>
        ) : null}

        <div className="sticky bottom-0 -mx-4 flex flex-col-reverse gap-2 border-t border-border bg-surface px-4 pt-3 sm:-mx-5 sm:flex-row sm:justify-end sm:px-5">
          <Button variant="ghost" onClick={onClose}>Отмена</Button>
          <Button isLoading={busy} disabled={!preview?.changed || !reason.trim() || busy} onClick={save}>Сохранить изменения</Button>
        </div>
      </div>
    </Drawer>
  )
}

function MoneyField({ id, label, value, onChange, disabled, help }: {
  id: string; label: string; value: string; onChange: (v: string) => void; disabled: boolean; help: string
}) {
  return (
    <Field label={label} htmlFor={id} help={help}>
      <Input id={id} inputMode="decimal" value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)}
        className={cn(disabled && 'bg-surface-muted')} aria-readonly={disabled} />
    </Field>
  )
}

function DiffRow({ label, before, after }: { label: string; before: string | null; after: string | null }) {
  return (
    <tr>
      <td className="py-1 pr-2">{label}</td>
      <td className="whitespace-nowrap text-right tabular-nums text-ink-secondary">{som(before)}</td>
      <td className="whitespace-nowrap text-right font-medium tabular-nums">{som(after)}</td>
      <td className="whitespace-nowrap text-right tabular-nums">{diff(before, after)}</td>
    </tr>
  )
}

const ACTION: Record<string, string> = {
  billing_month_edit: 'Изменение сумм месяца', billing_month_plan: 'План стоимости месяцев',
  billing_month_plan_redistribute: 'Перераспределение плана', billing_invoice_create: 'Выставлено начисление',
  billing_invoice_void: 'Начисление аннулировано', billing_adjustment: 'Корректировка начисления',
  billing_adjustment_void: 'Корректировка отменена',
}
const FIELD: Record<string, string> = { standard: 'Стандарт', plan: 'По плану', charge: 'Начисление' }

function historyLines(entry: { action: string; old_values: Record<string, unknown>; new_values: Record<string, unknown> }, month?: number): string[] {
  const o = entry.old_values, n = entry.new_values
  if (entry.action === 'billing_month_edit') {
    const lines = ((n.fields as string[] | undefined) ?? []).map((f) => `${FIELD[f] ?? f}: ${som(o[f] as string)} → ${som(n[f] as string)}`)
    if (o.final_course_price !== n.final_course_price) lines.push(`Итоговая стоимость курса: ${som(o.final_course_price as string)} → ${som(n.final_course_price as string)}`)
    const moved = n.redistributed as Record<string, [string, string]> | undefined
    for (const [m, [a, b]] of Object.entries(moved ?? {})) lines.push(`Месяц №${m} по плану: ${som(a)} → ${som(b)}`)
    const reissued = n.reissued as { from: string; to: string } | null | undefined
    if (reissued) lines.push(`Начисление ${reissued.from} заменено на ${reissued.to}`)
    if (n.difference) lines.push(n.difference === 'future' ? 'Разница перераспределена на будущие месяцы' : 'Разница учтена в стоимости курса')
    return lines
  }
  if (entry.action === 'billing_month_plan' && month) {
    const a = (o.months as Record<string, [string, string]> | undefined)?.[String(month)]
    const b = (n.months as Record<string, [string, string]> | undefined)?.[String(month)]
    return [`Стандарт ${som(a?.[0])} → ${som(b?.[0])}, по плану ${som(a?.[1])} → ${som(b?.[1])}`]
  }
  if (entry.action === 'billing_invoice_create') return [`Сумма ${som(n.amount as string)}`]
  if (entry.action === 'billing_invoice_void') return [n.replaced_by ? `Заменено начислением ${n.replaced_by as string}` : 'Аннулировано']
  if (entry.action === 'billing_adjustment') return [`Сумма ${som(n.amount as string)}`]
  return []
}

/** История сумм месяца: прежние значения, новые, причина, сотрудник, время, связанные начисления. */
export function MonthHistoryDrawer({ profile, month, onClose }: { profile: number; month?: number; onClose: () => void }) {
  const query = useQuery({ queryKey: [...FINANCE_KEY, 'month-history', profile, month ?? 0],
    queryFn: () => financeApi.monthHistory(profile, month) })
  return (
    <Drawer isOpen onClose={onClose} side="right" size="lg" title={month ? `История изменений: месяц №${month}` : 'История изменений графика'}>
      {query.isLoading ? <LoadingState /> : query.isError ? <p className="text-danger">Не удалось загрузить историю.</p>
        : !query.data?.length ? <p className="text-sm text-ink-secondary">Изменений не было.</p> : (
          <ol className="space-y-3 text-sm">
            {query.data.map((h) => (
              <li key={h.id} className="rounded-xl border border-border p-3">
                <p className="font-medium">{ACTION[h.action] ?? h.action}{h.invoice_number ? ` · ${h.invoice_number}` : ''}</p>
                <p className="text-xs text-ink-secondary">{formatDateTime(h.created_at)} · {h.actor}</p>
                <ul className="mt-1 space-y-0.5">{historyLines(h, month).map((l) => <li key={l}>{l}</li>)}</ul>
                {h.reason ? <p className="mt-1 text-ink-secondary">Причина: {h.reason}</p> : null}
              </li>
            ))}
          </ol>
        )}
    </Drawer>
  )
}
