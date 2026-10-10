import { useState } from 'react'
import { Plus } from 'lucide-react'

import { accountingApi } from '@/api/accounting'
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
import { useAccountingMutation, useAccountingOptions, useSalaryProfiles } from '@/hooks/useAccounting'
import { Field } from '@/features/worklog/formUi'
import type { AccountingOptions, RuleType, SalaryProfile, SalaryRule } from '@/types/accounting'

import { formatDate, som, today, useRunner } from './shared'

type Dialog = null | { kind: 'profile' } | { kind: 'rule'; profile: SalaryProfile } | { kind: 'version'; rule: SalaryRule } | { kind: 'stop'; rule: SalaryRule }

function rateText(rule: SalaryRule): string {
  if (rule.rule_type === 'PERCENT') return `${Number(rule.percentage)}% от стоимости курса`
  if (rule.percentage !== null) return `${Number(rule.percentage)}%`
  return `${som(rule.amount)} в месяц`
}

export function SalarySettingsPage() {
  const [search, setSearch] = useState('')
  const profiles = useSalaryProfiles(search)
  const options = useAccountingOptions()
  const [dialog, setDialog] = useState<Dialog>(null)
  const canEdit = options.data?.can_operate ?? false
  const close = () => setDialog(null)

  return (
    <div>
      <PageHeader
        title="Зарплатные правила"
        description="Схема оплаты каждого сотрудника. Изменение ставки создаёт новую версию правила — уже рассчитанные периоды не меняются."
        actions={canEdit ? <Button leftIcon={<Plus className="size-4" />} onClick={() => setDialog({ kind: 'profile' })}>Добавить сотрудника</Button> : null}
      />
      <FilterBar>
        <FilterField size="lg"><SearchInput value={search} onChange={setSearch} placeholder="Поиск по ФИО" /></FilterField>
      </FilterBar>

      {profiles.isLoading ? <LoadingState /> : profiles.isError ? <ErrorState onRetry={() => profiles.refetch()} /> :
        profiles.data?.results.length === 0 ? <EmptyState title="Зарплатных профилей нет" /> : (
          <div className="space-y-4">
            {profiles.data?.results.map((profile) => (
              <div key={profile.id} className="card p-4 sm:p-5">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="font-semibold text-ink">{profile.employee_name}</p>
                    <p className="text-sm text-ink-secondary">
                      {profile.display_position} · {profile.salary_type_display} · с {formatDate(profile.effective_from)}
                      {profile.effective_to ? ` по ${formatDate(profile.effective_to)}` : ''}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {!profile.is_active ? <Badge>Отключён</Badge> : null}
                    {canEdit ? (
                      <Button size="sm" variant="secondary" leftIcon={<Plus className="size-3.5" />}
                        onClick={() => setDialog({ kind: 'rule', profile })}>Правило</Button>
                    ) : null}
                  </div>
                </div>
                {profile.rules.length === 0 ? (
                  <p className="mt-3 text-sm text-danger">Ставка не настроена — расчёт покажет ошибку.</p>
                ) : (
                  <div className="mt-3 overflow-x-auto">
                    <table className="data-table">
                      <thead><tr><th>Правило</th><th>Ставка</th><th>Основание</th><th>Метод</th><th>Действует</th><th /></tr></thead>
                      <tbody>
                        {profile.rules.map((rule) => {
                          const closed = rule.effective_to !== null && rule.effective_to < today()
                          return (
                            <tr key={rule.id} className={closed ? 'opacity-60' : undefined}>
                              <td>#{rule.id} {rule.rule_type_display}{rule.description ? <p className="text-xs text-ink-muted">{rule.description}</p> : null}</td>
                              <td>{rateText(rule)}</td>
                              <td>{rule.group_name ? `группа ${rule.group_name}` : rule.program_name ? `программа ${rule.program_name}`
                                : rule.rule_type === 'PERCENT' ? 'все группы тренера' : '—'}</td>
                              <td className="text-xs">{rule.calculation_method_display}</td>
                              <td className="whitespace-nowrap text-sm">
                                {formatDate(rule.effective_from)} — {rule.effective_to ? formatDate(rule.effective_to) : 'без срока'}
                                {rule.previous_version ? <p className="text-xs text-ink-muted">версия правила #{rule.previous_version}</p> : null}
                              </td>
                              <td className="whitespace-nowrap text-right">
                                {canEdit && !closed && !rule.next_version && (rule.rule_type === 'FIXED' || rule.rule_type === 'PERCENT') ? (
                                  <>
                                    <Button size="sm" variant="ghost" onClick={() => setDialog({ kind: 'version', rule })}>Новая ставка</Button>
                                    <Button size="sm" variant="ghost" onClick={() => setDialog({ kind: 'stop', rule })}>Прекратить</Button>
                                  </>
                                ) : null}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

      {options.data && dialog?.kind === 'profile' ? <ProfileModal options={options.data} onClose={close} /> : null}
      {options.data && dialog?.kind === 'rule' ? <RuleModal options={options.data} profile={dialog.profile} onClose={close} /> : null}
      {dialog?.kind === 'version' ? <VersionModal rule={dialog.rule} onClose={close} /> : null}
      {dialog?.kind === 'stop' ? <StopModal rule={dialog.rule} onClose={close} /> : null}
    </div>
  )
}

function useSave() {
  const { run, busy } = useRunner()
  const mutate = useAccountingMutation(async (fn: () => Promise<unknown>) => fn())
  return { save: (fn: () => Promise<unknown>, message: string) => run(() => mutate.mutateAsync(fn), message), busy }
}

function ProfileModal({ options, onClose }: { options: AccountingOptions; onClose: () => void }) {
  const [form, setForm] = useState({ employee: '', salary_type: 'COMBINED', position: '', effective_from: today() })
  const { save, busy } = useSave()
  return (
    <Modal isOpen onClose={onClose} title="Зарплатный профиль сотрудника">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Сотрудник" required htmlFor="pf-emp">
          <Select id="pf-emp" value={form.employee} placeholder="Выберите" onChange={(e) => setForm({ ...form, employee: e.target.value })}
            options={options.employees.map((u) => ({ value: String(u.id), label: u.full_name }))} />
        </Field>
        <Field label="Тип оплаты" required htmlFor="pf-type">
          <Select id="pf-type" value={form.salary_type} options={options.salary_types} onChange={(e) => setForm({ ...form, salary_type: e.target.value })} />
        </Field>
        <Field label="Должность" htmlFor="pf-pos" help="Пусто — из профиля тренера или роли">
          <Input id="pf-pos" value={form.position} onChange={(e) => setForm({ ...form, position: e.target.value })} />
        </Field>
        <Field label="Действует с" required htmlFor="pf-from">
          <Input id="pf-from" type="date" value={form.effective_from} onChange={(e) => setForm({ ...form, effective_from: e.target.value })} />
        </Field>
      </div>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Отмена</Button>
        <Button isLoading={busy} disabled={!form.employee}
          onClick={async () => (await save(() => accountingApi.createProfile({ ...form, employee: Number(form.employee) }), 'Профиль создан')) && onClose()}>
          Сохранить
        </Button>
      </div>
    </Modal>
  )
}

function RuleModal({ options, profile, onClose }: { options: AccountingOptions; profile: SalaryProfile; onClose: () => void }) {
  // Тип правила = тип оплаты сотрудника: оклад или процент от стоимости курса.
  const ruleType: RuleType = profile.salary_type === 'PERCENT' ? 'PERCENT' : 'FIXED'
  const percent = ruleType === 'PERCENT'
  const [form, setForm] = useState({
    amount: '', percentage: '', program: '', group: '', calculation_method: '', description: '',
    effective_from: profile.effective_from > today() ? profile.effective_from : today(), effective_to: '',
  })
  const { save, busy } = useSave()
  const methods = options.methods[ruleType] ?? []
  const set = (patch: Partial<typeof form>) => setForm({ ...form, ...patch })
  const submit = () => save(() => accountingApi.createRule({
    employee_profile: profile.id,
    rule_type: ruleType,
    amount: percent ? null : form.amount,
    percentage: percent ? form.percentage : null,
    program: percent && form.program ? Number(form.program) : null,
    group: percent && form.group ? Number(form.group) : null,
    calculation_method: form.calculation_method || methods[0]?.value,
    description: form.description,
    effective_from: form.effective_from,
    effective_to: form.effective_to || null,
  }), 'Правило добавлено')

  return (
    <Modal isOpen onClose={onClose} title={`${percent ? 'Процент от стоимости курса' : 'Оклад'} — ${profile.employee_name}`} size="lg">
      {percent ? (
        <p className="mb-3 text-sm text-ink-secondary">
          За каждый завершённый цикл курса: студенты × стоимость курса × процент / 100. Стоимость и число уроков в цикле
          задаются в разделе «Курсы и циклы».
        </p>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2">
        {percent ? (
          <Field label="Процент тренера" required htmlFor="r-pct">
            <Input id="r-pct" type="number" min="0" max="100" step="0.01" value={form.percentage} onChange={(e) => set({ percentage: e.target.value })} />
          </Field>
        ) : (
          <Field label="Оклад в месяц, сом" required htmlFor="r-amount">
            <Input id="r-amount" type="number" min="0" step="0.01" value={form.amount} onChange={(e) => set({ amount: e.target.value })} />
          </Field>
        )}
        {percent ? (
          <>
            <Field label="Курс" htmlFor="r-prog" help="Пусто — все курсы">
              <Select id="r-prog" value={form.program} placeholder="Все курсы"
                options={options.courses.map((c) => ({ value: String(c.id), label: c.name }))}
                onChange={(e) => set({ program: e.target.value, group: '' })} />
            </Field>
            <Field label="Группа" htmlFor="r-group" help="Пусто — все группы, где сотрудник тренер">
              <Select id="r-group" value={form.group} placeholder="Все группы"
                options={options.groups.filter((g) => !form.program || String(g.course) === form.program).map((g) => ({ value: String(g.id), label: g.name }))}
                onChange={(e) => set({ group: e.target.value })} />
            </Field>
          </>
        ) : (
          <p className="self-end text-sm text-ink-secondary sm:col-span-1">
            Начисляется полной суммой за календарный месяц, на половины не делится. Аванс — частичная выплата этой суммы.
          </p>
        )}
        <Field label="Действует с" required htmlFor="r-from">
          <Input id="r-from" type="date" value={form.effective_from} onChange={(e) => set({ effective_from: e.target.value })} />
        </Field>
        <Field label="Действует по" htmlFor="r-to" help="Пусто — без срока">
          <Input id="r-to" type="date" value={form.effective_to} onChange={(e) => set({ effective_to: e.target.value })} />
        </Field>
      </div>
      <Field label="Комментарий" htmlFor="r-desc" className="mt-3">
        <Input id="r-desc" value={form.description} onChange={(e) => set({ description: e.target.value })} />
      </Field>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Отмена</Button>
        <Button isLoading={busy} disabled={percent ? !form.percentage : !form.amount}
          onClick={async () => (await submit()) && onClose()}>Добавить правило</Button>
      </div>
    </Modal>
  )
}

function VersionModal({ rule, onClose }: { rule: SalaryRule; onClose: () => void }) {
  const percent = rule.percentage !== null
  const [value, setValue] = useState(percent ? rule.percentage ?? '' : rule.amount ?? '')
  const [from, setFrom] = useState(today())
  const { save, busy } = useSave()
  return (
    <Modal isOpen onClose={onClose} title="Новая ставка">
      <p className="mb-3 text-sm text-ink-secondary">
        Текущее правило #{rule.id} закроется днём раньше выбранной даты; уже рассчитанные периоды сохранят прежнюю ставку.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={percent ? 'Процент' : 'Сумма, сом'} required htmlFor="v-val">
          <Input id="v-val" type="number" step="0.01" value={value} onChange={(e) => setValue(e.target.value)} />
        </Field>
        <Field label="Действует с" required htmlFor="v-from">
          <Input id="v-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        </Field>
      </div>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Отмена</Button>
        <Button isLoading={busy} disabled={!value || !from}
          onClick={async () => (await save(() => accountingApi.newRuleVersion(rule.id, { effective_from: from, ...(percent ? { percentage: value } : { amount: value }) }), 'Новая версия правила создана')) && onClose()}>
          Сохранить
        </Button>
      </div>
    </Modal>
  )
}

function StopModal({ rule, onClose }: { rule: SalaryRule; onClose: () => void }) {
  const [to, setTo] = useState(today())
  const [reason, setReason] = useState('')
  const { save, busy } = useSave()
  return (
    <Modal isOpen onClose={onClose} title="Прекратить действие правила">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Последний день действия" required htmlFor="s-to">
          <Input id="s-to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        </Field>
        <Field label="Причина" htmlFor="s-reason">
          <Input id="s-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
      </div>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Отмена</Button>
        <Button variant="danger" isLoading={busy} disabled={!to}
          onClick={async () => (await save(() => accountingApi.deactivateRule(rule.id, to, reason), 'Правило закрыто')) && onClose()}>
          Прекратить
        </Button>
      </div>
    </Modal>
  )
}
