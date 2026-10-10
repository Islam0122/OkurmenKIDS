import { useState } from 'react'
import { History, Info } from 'lucide-react'

import { accountingApi } from '@/api/accounting'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { Field } from '@/features/worklog/formUi'
import { useAccountingMutation } from '@/hooks/useAccounting'
import { extractErrorMessage } from '@/lib/apiError'
import type { AccountingOptions, RuleChangeEffects, RuleType, SalaryRule } from '@/types/accounting'

import { formatDate, today } from './shared'

const TYPES = [
  { value: 'FIXED', label: 'Фиксированный оклад' },
  { value: 'PERCENT', label: 'Процент от стоимости курса' },
]

function addDays(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00`)
  d.setDate(d.getDate() + n)
  const pad = (x: number) => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function firstOfNextMonth(iso: string): string {
  const [y, m] = iso.split('-').map(Number)
  return m === 12 ? `${y + 1}-01-01` : `${y}-${String(m + 1).padStart(2, '0')}-01`
}

function effectsText(e: RuleChangeEffects): string {
  const parts = []
  if (e.payrolls_recalculated.length) parts.push(`пересчитано черновых расчётов: ${e.payrolls_recalculated.length}`)
  if (e.payrolls_voided.length) parts.push(`аннулировано черновых расчётов: ${e.payrolls_voided.length}`)
  if (e.accruals_updated) parts.push(`обновлено начислений за циклы: ${e.accruals_updated}`)
  if (e.accruals_cancelled) parts.push(`отменено начислений за циклы: ${e.accruals_cancelled}`)
  if (e.payrolls_failed.length) parts.push(`не удалось пересчитать: ${e.payrolls_failed.map((f) => `#${f.payroll_id} — ${f.error}`).join('; ')}`)
  return parts.join(', ')
}

/**
 * Исправление правила зарплаты. Пока правило не попало в утверждённые
 * начисления — исправляется на месте (тип оплаты, ставка, основание, даты).
 * Если уже попало — история не меняется: правило заменяется с даты (старое
 * закрывается днём раньше). Все проверки — на backend.
 */
export function RuleCorrectionModal({ rule, options, onClose }: { rule: SalaryRule; options: AccountingOptions; onClose: () => void }) {
  const { showToast } = useToast()
  const mode: 'correct' | 'replace' = rule.usage.can_correct ? 'correct' : 'replace'
  const earliest = rule.usage.used_until ? addDays(rule.usage.used_until, 1) : addDays(rule.effective_from, 1)
  const [form, setForm] = useState({
    rule_type: (rule.rule_type === 'PERCENT' ? 'PERCENT' : 'FIXED') as RuleType,
    amount: rule.amount ?? '',
    percentage: rule.percentage ?? '',
    program: rule.program ? String(rule.program) : '',
    group: rule.group ? String(rule.group) : '',
    effective_from: mode === 'correct' ? rule.effective_from : (earliest > today() ? earliest : today()),
    effective_to: mode === 'correct' ? rule.effective_to ?? '' : '',
    description: rule.description,
    reason: '',
  })
  const [error, setError] = useState<string | null>(null)
  const set = (patch: Partial<typeof form>) => setForm({ ...form, ...patch })
  const percent = form.rule_type === 'PERCENT'
  const typeChanged = form.rule_type !== rule.rule_type
  const mutate = useAccountingMutation((fn: () => Promise<{ effects: RuleChangeEffects }>) => fn())

  const body = {
    rule_type: form.rule_type,
    amount: percent ? null : form.amount,
    percentage: percent ? form.percentage : null,
    program: percent && form.program ? Number(form.program) : null,
    group: percent && form.group ? Number(form.group) : null,
    effective_from: form.effective_from,
    effective_to: form.effective_to || null,
    description: form.description,
    reason: form.reason.trim(),
  }
  const valid = Boolean(form.reason.trim() && form.effective_from && (percent ? form.percentage : form.amount))

  const submit = async () => {
    setError(null)
    try {
      const result = await mutate.mutateAsync(() => (mode === 'correct'
        ? accountingApi.correctRule(rule.id, body)
        : accountingApi.replaceRule(rule.id, body)))
      const details = effectsText(result.effects)
      showToast(`${mode === 'correct' ? 'Правило исправлено' : 'Правило заменено'}${details ? `: ${details}` : ''}`, 'success')
      onClose()
    } catch (e) {
      setError(extractErrorMessage(e))
    }
  }

  return (
    <Modal isOpen onClose={onClose} size="lg"
      title={mode === 'correct' ? `Исправить правило #${rule.id} — ${rule.employee_name}` : `Заменить правило #${rule.id} с даты — ${rule.employee_name}`}>
      {mode === 'correct' ? (
        <div className="mb-3 flex gap-2 rounded-lg bg-surface-muted p-3 text-sm text-ink-secondary">
          <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
          <p>
            Правило ещё не попало в утверждённые начисления, поэтому его можно исправить на месте.
            {rule.usage.draft_payrolls ? ` Черновых расчётов с этим правилом: ${rule.usage.draft_payrolls} — они будут пересчитаны.` : ''}
            {rule.usage.open_accruals ? ` Неутверждённых начислений за циклы: ${rule.usage.open_accruals} — пересчитаются или отменятся.` : ''}
            {typeChanged ? ' Тип оплаты сотрудника тоже изменится.' : ''}
          </p>
        </div>
      ) : (
        <div className="mb-3 flex gap-2 rounded-lg bg-warning-soft p-3 text-sm text-warning">
          <History className="mt-0.5 size-4 shrink-0" aria-hidden />
          <p>
            Правило уже использовано в утверждённых начислениях{rule.usage.used_until ? ` (до ${formatDate(rule.usage.used_until)})` : ''},
            поэтому история не меняется: старое правило закроется днём раньше выбранной даты, а новое начнёт действовать с неё.
            {typeChanged ? ' Смена типа оплаты — только с 1-го числа месяца.' : ''}
          </p>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Тип оплаты" required htmlFor="rc-type">
          <Select id="rc-type" value={form.rule_type} options={TYPES}
            onChange={(e) => {
              const next = e.target.value as RuleType
              const from = mode === 'replace' && next !== rule.rule_type && !form.effective_from.endsWith('-01')
                ? firstOfNextMonth(form.effective_from) : form.effective_from
              set({ rule_type: next, effective_from: from })
            }} />
        </Field>
        {percent ? (
          <Field label="Процент тренера" required htmlFor="rc-pct">
            <Input id="rc-pct" type="number" min="0" max="100" step="0.01" value={form.percentage} onChange={(e) => set({ percentage: e.target.value })} />
          </Field>
        ) : (
          <Field label="Оклад в месяц, сом" required htmlFor="rc-amount">
            <Input id="rc-amount" type="number" min="0" step="0.01" value={form.amount} onChange={(e) => set({ amount: e.target.value })} />
          </Field>
        )}
        {percent ? (
          <>
            <Field label="Курс" htmlFor="rc-prog" help="Пусто — все курсы">
              <Select id="rc-prog" value={form.program} placeholder="Все курсы"
                options={options.courses.map((c) => ({ value: String(c.id), label: c.name }))}
                onChange={(e) => set({ program: e.target.value, group: '' })} />
            </Field>
            <Field label="Группа" htmlFor="rc-group" help="Пусто — все группы, где сотрудник тренер">
              <Select id="rc-group" value={form.group} placeholder="Все группы"
                options={options.groups.filter((g) => !form.program || String(g.course) === form.program).map((g) => ({ value: String(g.id), label: g.name }))}
                onChange={(e) => set({ group: e.target.value })} />
            </Field>
          </>
        ) : null}
        <Field label={mode === 'correct' ? 'Действует с' : 'Новое правило действует с'} required htmlFor="rc-from"
          help={mode === 'replace' ? `Не раньше ${formatDate(earliest)}` : undefined}>
          <Input id="rc-from" type="date" value={form.effective_from} min={mode === 'replace' ? earliest : undefined}
            onChange={(e) => set({ effective_from: e.target.value })} />
        </Field>
        <Field label="Действует по" htmlFor="rc-to" help="Пусто — без срока">
          <Input id="rc-to" type="date" value={form.effective_to} onChange={(e) => set({ effective_to: e.target.value })} />
        </Field>
      </div>
      <Field label="Комментарий к правилу" htmlFor="rc-desc" className="mt-3">
        <Input id="rc-desc" value={form.description} onChange={(e) => set({ description: e.target.value })} />
      </Field>
      <Field label={mode === 'correct' ? 'Что и почему исправляется' : 'Причина замены'} required htmlFor="rc-reason" className="mt-3"
        help="Сохраняется в журнале изменений">
        <Textarea id="rc-reason" rows={2} value={form.reason} onChange={(e) => set({ reason: e.target.value })} />
      </Field>
      {error ? <p role="alert" className="mt-3 rounded-lg bg-danger-soft p-3 text-sm text-danger">{error}</p> : null}
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Отмена</Button>
        <Button isLoading={mutate.isPending} disabled={!valid} onClick={submit}>
          {mode === 'correct' ? 'Исправить правило' : 'Заменить с даты'}
        </Button>
      </div>
    </Modal>
  )
}
