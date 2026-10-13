import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { History, Info, Pencil, Plus } from 'lucide-react'

import { accountingApi } from '@/api/accounting'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { Field } from '@/features/worklog/formUi'
import { useAccountingMutation, useDeductionRules } from '@/hooks/useAccounting'
import { extractErrorMessage } from '@/lib/apiError'
import type { AccountingOptions, DeductionEffects, DeductionRule, DeductionRuleBody } from '@/types/accounting'

import { formatDate, formatDateTime, som, today } from './shared'

const KINDS = [
  { value: 'TAX', label: 'Налог' },
  { value: 'CONTRIBUTION', label: 'Обязательный взнос' },
  { value: 'OTHER', label: 'Другое удержание' },
]
const FREQUENCIES = [
  { value: 'MONTHLY', label: 'Ежемесячно' },
  { value: 'PERIOD', label: 'Ежемесячно в указанный период' },
  { value: 'ONCE', label: 'Однократно' },
]
const SCOPES = [
  { value: 'EMPLOYEE', label: 'Сотрудник' },
  { value: 'DEPARTMENT', label: 'Направление' },
  { value: 'ALL', label: 'Все сотрудники' },
]

function firstOfNextMonth(iso: string): string {
  const [y, m] = iso.split('-').map(Number)
  return m === 12 ? `${y + 1}-01-01` : `${y}-${String(m + 1).padStart(2, '0')}-01`
}

function effectsText(e: DeductionEffects): string {
  const parts = []
  if (e.payrolls_recalculated.length) parts.push(`пересчитано черновых расчётов: ${e.payrolls_recalculated.length}`)
  if (e.payrolls_failed.length) parts.push(`не удалось пересчитать: ${e.payrolls_failed.map((f) => `#${f.payroll_id} — ${f.error}`).join('; ')}`)
  return parts.join(', ')
}

function whom(rule: DeductionRule): string {
  if (rule.scope === 'EMPLOYEE') return rule.employee_name
  if (rule.scope === 'DEPARTMENT') return `направление «${rule.department_display}»`
  return 'все сотрудники'
}

/** «Налоги и удержания»: фиксированные суммы, которые бухгалтер задаёт вручную.
 * Ежемесячное удержание применяется один раз за месяц на сотрудника, сколько бы
 * у него ни было начислений (это гарантирует сервер). */
export function DeductionRulesSection({ options, canEdit }: { options: AccountingOptions; canEdit: boolean }) {
  const rules = useDeductionRules({ current: true })
  const [dialog, setDialog] = useState<null | { kind: 'create' } | { kind: 'change' | 'history'; rule: DeductionRule }>(null)
  const close = () => setDialog(null)

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-3xl text-sm text-ink-secondary">
          Суммы задаёт бухгалтер; названия и назначение — тоже. Обязательные налоги и взносы должны соответствовать
          действующему законодательству. Ежемесячное удержание берётся один раз за месяц, даже если у сотрудника
          несколько начислений, и никогда не делает сумму к выплате отрицательной.
        </p>
        {canEdit ? <Button leftIcon={<Plus className="size-4" />} onClick={() => setDialog({ kind: 'create' })}>Добавить удержание</Button> : null}
      </div>
      {rules.isLoading ? <LoadingState /> : rules.isError ? <ErrorState onRetry={() => rules.refetch()} /> :
        !rules.data?.results.length ? <EmptyState title="Удержаний нет" description={canEdit ? 'Добавьте налог или другое удержание с фиксированной суммой.' : undefined} /> : (
          <div className="card overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr><th>Удержание</th><th>Кому</th><th className="text-right">Сумма</th><th>Периодичность</th><th>Действует</th><th>Статус</th><th /></tr>
              </thead>
              <tbody>
                {rules.data.results.map((rule) => {
                  const closed = rule.effective_to !== null && rule.effective_to < today()
                  return (
                    <tr key={rule.id} className={!rule.is_active || closed ? 'opacity-60' : undefined}>
                      <td>
                        {rule.name}
                        <p className="text-xs text-ink-muted">{rule.kind_display}{rule.description ? ` · ${rule.description}` : ''}</p>
                      </td>
                      <td className="text-sm">{whom(rule)}</td>
                      <td className="whitespace-nowrap text-right">{som(rule.amount)}</td>
                      <td className="text-sm">{rule.frequency_display}</td>
                      <td className="whitespace-nowrap text-sm">
                        {formatDate(rule.effective_from)} — {rule.frequency === 'ONCE' ? 'однократно' : rule.effective_to ? formatDate(rule.effective_to) : 'без срока'}
                        {rule.previous_version ? <p className="text-xs text-ink-muted">новая версия правила</p> : null}
                        {rule.usage.used_until ? <p className="text-xs text-ink-muted">в утверждённых расчётах до {formatDate(rule.usage.used_until)}</p> : null}
                      </td>
                      <td>{rule.is_active ? <Badge tone="success">Включено</Badge> : <Badge>Отключено</Badge>}</td>
                      <td className="whitespace-nowrap text-right">
                        <Button size="sm" variant="ghost" leftIcon={<History className="size-3.5" />} onClick={() => setDialog({ kind: 'history', rule })}>История</Button>
                        {canEdit ? (
                          <Button size="sm" variant="ghost" leftIcon={<Pencil className="size-3.5" />} onClick={() => setDialog({ kind: 'change', rule })}>Изменить</Button>
                        ) : null}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      {dialog?.kind === 'create' ? <DeductionModal options={options} onClose={close} /> : null}
      {dialog?.kind === 'change' ? <DeductionModal options={options} rule={dialog.rule} onClose={close} /> : null}
      {dialog?.kind === 'history' ? <HistoryModal rule={dialog.rule} onClose={close} /> : null}
    </div>
  )
}

function DeductionModal({ options, rule, onClose }: { options: AccountingOptions; rule?: DeductionRule; onClose: () => void }) {
  const { showToast } = useToast()
  const used = Boolean(rule && !rule.usage.can_correct)
  const [form, setForm] = useState({
    name: rule?.name ?? '',
    kind: rule?.kind ?? 'TAX',
    amount: rule?.amount ?? '',
    frequency: rule?.frequency ?? 'MONTHLY',
    scope: rule?.scope ?? 'EMPLOYEE',
    employee: rule?.employee ? String(rule.employee) : '',
    department: rule?.department ?? '',
    effective_from: rule?.effective_from ?? today().slice(0, 8) + '01',
    effective_to: rule?.effective_to ?? '',
    is_active: rule?.is_active ?? true,
    description: rule?.description ?? '',
    reason: '',
  })
  const [error, setError] = useState<string | null>(null)
  const set = (patch: Partial<typeof form>) => setForm({ ...form, ...patch })
  const mutate = useAccountingMutation((fn: () => Promise<{ effects: DeductionEffects }>) => fn())
  const material = rule ? (
    form.amount !== rule.amount || form.kind !== rule.kind || form.frequency !== rule.frequency || form.scope !== rule.scope
    || form.employee !== (rule.employee ? String(rule.employee) : '') || form.department !== rule.department
  ) : false
  const needsDate = used && material
  const nextMonth = rule?.usage.used_until ? firstOfNextMonth(rule.usage.used_until) : ''

  const body: DeductionRuleBody = {
    name: form.name.trim(), kind: form.kind, amount: form.amount, frequency: form.frequency, scope: form.scope,
    employee: form.scope === 'EMPLOYEE' && form.employee ? Number(form.employee) : null,
    department: form.scope === 'DEPARTMENT' ? form.department : '', effective_from: form.effective_from,
    effective_to: form.effective_to || null, is_active: form.is_active, description: form.description,
  }
  const valid = Boolean(form.name.trim() && Number(form.amount) > 0 && form.effective_from
    && (form.scope !== 'EMPLOYEE' || form.employee) && (form.scope !== 'DEPARTMENT' || form.department)
    && (form.frequency !== 'PERIOD' || form.effective_to) && (!rule || form.reason.trim()))

  const submit = async () => {
    setError(null)
    try {
      const result = await mutate.mutateAsync(() => {
        if (!rule) return accountingApi.createDeductionRule(body)
        const changes: Partial<DeductionRuleBody> & { reason: string } = { reason: form.reason.trim() }
        for (const key of Object.keys(body) as (keyof DeductionRuleBody)[]) {
          const before = key === 'employee' ? rule.employee : rule[key]
          if (body[key] !== before) Object.assign(changes, { [key]: body[key] })
        }
        return accountingApi.changeDeductionRule(rule.id, changes)
      })
      const details = effectsText(result.effects)
      showToast(`${rule ? 'Удержание изменено' : 'Удержание добавлено'}${details ? `: ${details}` : ''}`, 'success')
      onClose()
    } catch (e) {
      setError(extractErrorMessage(e))
    }
  }

  return (
    <Modal isOpen onClose={onClose} size="lg" title={rule ? `Изменить удержание «${rule.name}»` : 'Новое удержание'}>
      {used ? (
        <div className="mb-3 flex gap-2 rounded-lg bg-warning-soft p-3 text-sm text-warning">
          <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
          <p>
            Удержание уже вошло в утверждённые расчёты{rule?.usage.used_until ? ` (до ${formatDate(rule.usage.used_until)})` : ''} — они не меняются.
            Название, комментарий, включение и дату окончания можно изменить сразу; новая сумма, вид, периодичность
            или круг сотрудников начнут действовать с 1-го числа выбранного месяца как новая версия.
          </p>
        </div>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Название" required htmlFor="dr-name">
          <Input id="dr-name" value={form.name} placeholder="Например: Налог" onChange={(e) => set({ name: e.target.value })} />
        </Field>
        <Field label="Вид" required htmlFor="dr-kind">
          <Select id="dr-kind" value={form.kind} options={KINDS} onChange={(e) => set({ kind: e.target.value as DeductionRuleBody['kind'] })} />
        </Field>
        <Field label="Сумма, сом" required htmlFor="dr-amount" help="Фиксированная сумма за месяц (или однократно)">
          <Input id="dr-amount" type="number" min="0.01" step="0.01" value={form.amount} onChange={(e) => set({ amount: e.target.value })} />
        </Field>
        <Field label="Периодичность" required htmlFor="dr-freq">
          <Select id="dr-freq" value={form.frequency} options={FREQUENCIES} onChange={(e) => set({ frequency: e.target.value as DeductionRuleBody['frequency'] })} />
        </Field>
        <Field label="Кому применяется" required htmlFor="dr-scope">
          <Select id="dr-scope" value={form.scope} options={SCOPES} onChange={(e) => set({ scope: e.target.value as DeductionRuleBody['scope'] })} />
        </Field>
        {form.scope === 'EMPLOYEE' ? (
          <Field label="Сотрудник" required htmlFor="dr-emp">
            <Select id="dr-emp" value={form.employee} placeholder="Выберите сотрудника"
              options={options.employees.map((e) => ({ value: String(e.id), label: e.full_name }))} onChange={(e) => set({ employee: e.target.value })} />
          </Field>
        ) : form.scope === 'DEPARTMENT' ? (
          <Field label="Направление" required htmlFor="dr-dep">
            <Select id="dr-dep" value={form.department} placeholder="Выберите направление" options={options.departments}
              onChange={(e) => set({ department: e.target.value })} />
          </Field>
        ) : <div />}
        <Field label={needsDate ? 'Новая версия действует с' : 'Действует с'} required htmlFor="dr-from"
          help={needsDate && nextMonth ? `С 1-го числа, не раньше ${formatDate(nextMonth)}` : form.frequency === 'ONCE' ? 'Удерживается в месяце этой даты' : undefined}>
          <Input id="dr-from" type="date" value={form.effective_from} min={needsDate ? nextMonth : undefined}
            onChange={(e) => set({ effective_from: e.target.value })} />
        </Field>
        <Field label="Действует по" required={form.frequency === 'PERIOD'} htmlFor="dr-to" help="Пусто — без срока">
          <Input id="dr-to" type="date" value={form.effective_to} disabled={form.frequency === 'ONCE'}
            onChange={(e) => set({ effective_to: e.target.value })} />
        </Field>
      </div>
      <Field label="Комментарий" htmlFor="dr-desc" className="mt-3">
        <Input id="dr-desc" value={form.description} onChange={(e) => set({ description: e.target.value })} />
      </Field>
      <label className="mt-3 flex items-center gap-2 text-sm">
        <input type="checkbox" checked={form.is_active} onChange={(e) => set({ is_active: e.target.checked })} />
        Правило включено
      </label>
      {rule ? (
        <Field label="Причина изменения" required htmlFor="dr-reason" className="mt-3" help="Сохраняется в истории правила">
          <Textarea id="dr-reason" rows={2} value={form.reason} onChange={(e) => set({ reason: e.target.value })} />
        </Field>
      ) : null}
      {error ? <p role="alert" className="mt-3 rounded-lg bg-danger-soft p-3 text-sm text-danger">{error}</p> : null}
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Отмена</Button>
        <Button isLoading={mutate.isPending} disabled={!valid} onClick={submit}>{rule ? 'Сохранить' : 'Добавить'}</Button>
      </div>
    </Modal>
  )
}

const ACTIONS: Record<string, string> = {
  deduction_rule_create: 'Создано',
  deduction_rule_correct: 'Исправлено',
  deduction_rule_new_version: 'Новая версия',
}
const FIELDS: Record<string, string> = {
  name: 'название', kind: 'вид', amount: 'сумма', frequency: 'периодичность', scope: 'кому', employee: 'сотрудник',
  department: 'направление', effective_from: 'с', effective_to: 'по', is_active: 'включено', description: 'комментарий',
}

function HistoryModal({ rule, onClose }: { rule: DeductionRule; onClose: () => void }) {
  const history = useQuery({
    queryKey: ['accounting', 'deduction-rules', 'history', rule.id],
    queryFn: () => accountingApi.deductionRuleHistory(rule.id),
  })
  const data = history.data
  return (
    <Modal isOpen onClose={onClose} size="lg" title={`История: ${rule.name}`}>
      {history.isError ? <ErrorState onRetry={() => history.refetch()} /> : !data ? <LoadingState /> : (
        <>
          <p className="mb-2 text-sm font-medium text-ink">Версии</p>
          <ul className="mb-4 space-y-1 text-sm text-ink-secondary">
            {data.versions.map((v) => (
              <li key={v.id}>{som(v.amount)} · {v.frequency_display} · {formatDate(v.effective_from)} — {v.effective_to ? formatDate(v.effective_to) : 'без срока'}{v.is_active ? '' : ' · отключено'}</li>
            ))}
          </ul>
          <p className="mb-2 text-sm font-medium text-ink">Изменения</p>
          <ul className="card divide-y divide-border">
            {data.audit.map((h) => (
              <li key={h.id} className="px-4 py-2.5 text-sm">
                <span className="text-ink-muted">{formatDateTime(h.created_at)}</span> · <b>{ACTIONS[h.action] ?? h.action}</b> · {h.actor_name}
                {h.reason ? <p className="text-ink-secondary">Причина: {h.reason}</p> : null}
                {h.action !== 'deduction_rule_create' ? (
                  <p className="text-xs text-ink-muted">
                    {Object.keys(h.new_values).filter((k) => k in FIELDS && String(h.old_values[k] ?? '') !== String(h.new_values[k] ?? ''))
                      .map((k) => `${FIELDS[k]}: ${String(h.old_values[k] ?? '—')} → ${String(h.new_values[k] ?? '—')}`).join(' · ')}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </>
      )}
    </Modal>
  )
}
