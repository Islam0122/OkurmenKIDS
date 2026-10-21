import { useState } from 'react'
import { Plus, UserPlus } from 'lucide-react'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'

import { billingApi } from '@/api/billing'
import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { useToast } from '@/components/ui/Toast'
import { Field } from '@/features/worklog/formUi'
import type { BillingCapabilities, BillingFilters, BillingOptions, PaymentState } from '@/types/billing'

import { formatDate, som, today, useRunner } from './shared'

const STATE: Record<PaymentState, { tone: BadgeTone; label: string }> = {
  paid: { tone: 'success', label: 'Оплачено' },
  awaiting: { tone: 'warning', label: 'Ожидает оплаты' },
  overdue: { tone: 'danger', label: 'Просрочено' },
  draft: { tone: 'muted', label: 'Скидка на согласовании' },
}

type RowAction = (target: { profile: number; student: string }) => void

/** Все студенты LMS: подключены ли к оплате, долг, аванс, текущий пакет. */
export function BillingStudents({ filters, options, caps, onPay, onContact }: {
  filters: BillingFilters
  options?: BillingOptions
  caps?: BillingCapabilities
  onPay?: RowAction
  onContact?: RowAction
}) {
  const [search, setSearch] = useState('')
  const [registered, setRegistered] = useState('')
  const [state, setState] = useState('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<number[]>([])
  const [registering, setRegistering] = useState(false)
  const [creatingPlan, setCreatingPlan] = useState(false)
  const canRegister = Boolean(caps?.is_manager || caps?.is_billing_admin)
  const students = useQuery({
    queryKey: ['billing', 'students', filters.group, search, registered, state, page],
    queryFn: () => billingApi.students({
      group: filters.group, search: search || undefined, registered: registered || undefined,
      state: state || undefined, page,
    }),
    placeholderData: keepPreviousData,
  })
  const plans = options?.plans ?? []
  const toggle = (id: number) => setSelected((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]))

  return (
    <div>
      {plans.length === 0 ? (
        <div className="mb-4 rounded-xl border border-warning/20 bg-warning-soft p-3 text-sm text-warning">
          Тарифов ещё нет — без тарифа студента нельзя подключить к оплате.
          {caps?.can_manage_plans ? (
            <Button size="sm" className="ml-3" leftIcon={<Plus className="size-4" />} onClick={() => setCreatingPlan(true)}>
              Создать тариф
            </Button>
          ) : ' Тариф создаёт директор или администратор.'}
        </div>
      ) : null}
      <FilterBar>
        <FilterField size="lg">
          <SearchInput value={search} placeholder="Студент или телефон родителя"
            onChange={(v) => { setSearch(v); setPage(1) }} />
        </FilterField>
        <FilterField>
          <Select aria-label="Подключение к оплате" value={registered} placeholder="Все студенты"
            options={[{ value: 'yes', label: 'Подключены к оплате' }, { value: 'no', label: 'Не подключены' }]}
            onChange={(e) => { setRegistered(e.target.value); setPage(1) }} />
        </FilterField>
        <FilterField>
          <Select aria-label="Состояние оплаты" value={state} placeholder="Любая оплата"
            options={[{ value: 'debt', label: 'Есть долг' }, { value: 'overdue', label: 'Просрочка' }]}
            onChange={(e) => { setState(e.target.value); setPage(1) }} />
        </FilterField>
        {canRegister ? (
          <FilterField>
            <div className="flex flex-wrap gap-2">
              <Button leftIcon={<UserPlus className="size-4" />} disabled={plans.length === 0}
                onClick={() => setRegistering(true)}>
                {selected.length ? `Подключить выбранных (${selected.length})` : 'Подключить к оплате'}
              </Button>
              {caps?.can_manage_plans && plans.length > 0 ? (
                <Button variant="ghost" leftIcon={<Plus className="size-4" />} onClick={() => setCreatingPlan(true)}>Тариф</Button>
              ) : null}
            </div>
          </FilterField>
        ) : null}
      </FilterBar>

      {students.isLoading ? <LoadingState /> : students.isError || !students.data ? <ErrorState onRetry={() => students.refetch()} /> :
        students.data.results.length === 0 ? <EmptyState title="Студентов не найдено" /> : (
          <>
            <div className="card overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    {canRegister ? <th /> : null}
                    <th>Студент</th><th>Группа</th><th>Направление / тариф</th><th>Пакет</th>
                    <th className="text-right">Долг</th><th className="text-right">Аванс</th><th>Срок</th><th>Оплата</th><th />
                  </tr>
                </thead>
                <tbody>
                  {students.data.results.map((st) => {
                    const rows = st.profiles.length ? st.profiles : [null]
                    return rows.map((p, i) => (
                      <tr key={`${st.id}-${p?.id ?? 'none'}`}>
                        {canRegister ? (
                          <td>{i === 0 ? (
                            <input type="checkbox" aria-label={`Выбрать ${st.name}`} checked={selected.includes(st.id)}
                              onChange={() => toggle(st.id)} />
                          ) : null}</td>
                        ) : null}
                        <td>{i === 0 ? <>{st.name}<div className="text-xs text-ink-muted">{st.parent_phone}</div></> : null}</td>
                        <td>{i === 0 ? st.group_name ?? '—' : null}</td>
                        {p ? (
                          <>
                            <td>{p.subject_name ?? 'Все уроки'}<div className="text-xs text-ink-muted">{p.plan_name}</div></td>
                            <td>{p.package ? `№${p.package.number}: ${p.package.used} из ${p.package.total}` : '—'}</td>
                            <td className="text-right font-medium">{Number(p.debt) > 0 ? som(p.debt) : '—'}</td>
                            <td className="text-right">{Number(p.credit) > 0 ? som(p.credit) : '—'}</td>
                            <td>{formatDate(p.next_due)}</td>
                            <td>
                              <Badge tone={STATE[p.payment_state].tone}>{STATE[p.payment_state].label}</Badge>
                              {p.status === 'PAUSED' ? <Badge className="ml-1">Пауза</Badge> : null}
                            </td>
                            <td className="whitespace-nowrap text-right">
                              {onPay ? <Button size="sm" variant="ghost" onClick={() => onPay({ profile: p.id, student: st.name })}>Платёж</Button> : null}
                              {onContact ? <Button size="sm" variant="ghost" onClick={() => onContact({ profile: p.id, student: st.name })}>Контакт</Button> : null}
                            </td>
                          </>
                        ) : (
                          <td colSpan={7}><Badge>Не подключён к оплате</Badge></td>
                        )}
                      </tr>
                    ))
                  })}
                </tbody>
              </table>
            </div>
            <Pagination page={page} pageSize={50} totalCount={students.data.count} onPageChange={setPage} />
          </>
        )}
      {registering ? (
        <RegisterModal options={options} caps={caps} selected={selected} group={filters.group}
          onClose={() => setRegistering(false)} onDone={() => setSelected([])} />
      ) : null}
      {creatingPlan ? <PlanModal options={options} onClose={() => setCreatingPlan(false)} /> : null}
    </div>
  )
}

function RegisterModal({ options, caps, selected, group, onClose, onDone }: {
  options?: BillingOptions
  caps?: BillingCapabilities
  selected: number[]
  group?: number
  onClose: () => void
  onDone: () => void
}) {
  const client = useQueryClient()
  const { showToast } = useToast()
  const { run, busy } = useRunner()
  const scopes = [
    ...(selected.length ? [{ value: 'selected', label: `Выбранные студенты (${selected.length})` }] : []),
    ...(group ? [{ value: 'group', label: 'Вся выбранная группа' }] : []),
    { value: 'all', label: 'Все активные студенты' },
  ]
  const [form, setForm] = useState({
    plan: String(options?.plans[0]?.id ?? ''), scope: scopes[0].value, start_date: today(), accountant: '',
    prepaid: false, prepaid_reason: '',
  })
  return (
    <Modal isOpen onClose={onClose} title="Подключить студентов к оплате">
      <div className="space-y-3">
        <Field label="Тариф" htmlFor="reg-plan" required>
          <Select id="reg-plan" value={form.plan} options={(options?.plans ?? []).map((p) => ({ value: String(p.id), label: p.name }))}
            onChange={(e) => setForm({ ...form, plan: e.target.value })} />
        </Field>
        <Field label="Кого подключить" htmlFor="reg-scope">
          <Select id="reg-scope" value={form.scope} options={scopes} onChange={(e) => setForm({ ...form, scope: e.target.value })} />
        </Field>
        <Field label="Считать уроки с" htmlFor="reg-start" help="Уроки до этой даты не списываются. Уже подключённые к этому направлению пропускаются.">
          <Input id="reg-start" type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
        </Field>
        <Field label="Ответственный бухгалтер" htmlFor="reg-acc">
          <Select id="reg-acc" value={form.accountant} placeholder="Не назначен"
            options={(options?.accountants ?? []).map((a) => ({ value: String(a.id), label: a.name }))}
            onChange={(e) => setForm({ ...form, accountant: e.target.value })} />
        </Field>
        {caps?.is_billing_admin ? (
          <>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.prepaid} onChange={(e) => setForm({ ...form, prepaid: e.target.checked })} />
              Первый пакет уже оплачен до подключения учёта
            </label>
            {form.prepaid ? (
              <Field label="Основание" htmlFor="reg-reason" required>
                <Input id="reg-reason" value={form.prepaid_reason} placeholder="Например: оплачено наличными в сентябре"
                  onChange={(e) => setForm({ ...form, prepaid_reason: e.target.value })} />
              </Field>
            ) : null}
          </>
        ) : null}
        <p className="text-xs text-ink-muted">Каждому студенту сразу создаётся первый пакет и начисление по тарифу.</p>
      </div>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Отмена</Button>
        <Button isLoading={busy} disabled={!form.plan || (form.prepaid && !form.prepaid_reason.trim())} onClick={async () => {
          const ok = await run(async () => {
            const result = await billingApi.bulkRegister({
              plan: Number(form.plan),
              students: form.scope === 'selected' ? selected : undefined,
              group: form.scope === 'group' ? group : undefined,
              all_active: form.scope === 'all',
              start_date: form.start_date || null,
              responsible_accountant: form.accountant ? Number(form.accountant) : null,
              prepaid_first_package: form.prepaid,
              prepaid_reason: form.prepaid_reason,
            })
            showToast(`Подключено: ${result.created}, пропущено: ${result.skipped.length}`, 'success')
            await client.invalidateQueries({ queryKey: ['billing'] })
          })
          if (ok) {
            onDone()
            onClose()
          }
        }}>Подключить</Button>
      </div>
    </Modal>
  )
}

function PlanModal({ options, onClose }: { options?: BillingOptions; onClose: () => void }) {
  const client = useQueryClient()
  const { run, busy } = useRunner()
  const [form, setForm] = useState({ name: '', subject: '', lessons: '12', price: '', due: '5', from: today() })
  return (
    <Modal isOpen onClose={onClose} title="Новый тариф">
      <div className="space-y-3">
        <Field label="Название" htmlFor="plan-name" required>
          <Input id="plan-name" value={form.name} placeholder="IT — 12 уроков" onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </Field>
        <Field label="Направление" htmlFor="plan-subject" help="Уроки какого предмета входят в пакет. Пусто — все уроки группы.">
          <Select id="plan-subject" value={form.subject} placeholder="Все уроки группы"
            options={(options?.subjects ?? []).map((s) => ({ value: String(s.id), label: s.name }))}
            onChange={(e) => setForm({ ...form, subject: e.target.value })} />
        </Field>
        <Field label="Уроков в пакете" htmlFor="plan-lessons" required>
          <Input id="plan-lessons" type="number" min={1} value={form.lessons} onChange={(e) => setForm({ ...form, lessons: e.target.value })} />
        </Field>
        <Field label="Стоимость пакета, сом" htmlFor="plan-price" required>
          <Input id="plan-price" inputMode="decimal" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} />
        </Field>
        <Field label="Срок оплаты, дней" htmlFor="plan-due">
          <Input id="plan-due" type="number" min={0} value={form.due} onChange={(e) => setForm({ ...form, due: e.target.value })} />
        </Field>
        <Field label="Действует с" htmlFor="plan-from" required>
          <Input id="plan-from" type="date" value={form.from} onChange={(e) => setForm({ ...form, from: e.target.value })} />
        </Field>
      </div>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Отмена</Button>
        <Button isLoading={busy} disabled={!form.name.trim() || !form.price || !form.lessons} onClick={async () => {
          const ok = await run(async () => {
            await billingApi.createPlan({
              name: form.name.trim(), subject: form.subject ? Number(form.subject) : null,
              lessons_per_package: Number(form.lessons), package_price: form.price, effective_from: form.from,
              payment_due_days: Number(form.due) || 0,
            })
            await client.invalidateQueries({ queryKey: ['billing'] })
          }, 'Тариф создан')
          if (ok) onClose()
        }}>Создать</Button>
      </div>
    </Modal>
  )
}
