import { useEffect, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Plus } from 'lucide-react'

import { financeApi } from '@/api/finance'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { DataTable } from '@/components/ui/DataTable'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { Field } from '@/features/worklog/formUi'
import type { FinanceSettings, Plan } from '@/types/finance'

import { FINANCE_KEY, Loadable, formatDate, formatDateTime, som, today, useFinanceMe, useFinanceOptions, useInvalidateFinance, useRunner } from './ui'

// ---------------------------------------------------------------------------
// Тарифы и программы
// ---------------------------------------------------------------------------

export function PlansPage() {
  const me = useFinanceMe()
  const query = useQuery({ queryKey: [...FINANCE_KEY, 'plans'], queryFn: financeApi.plans })
  const [creating, setCreating] = useState(false)
  const [pricing, setPricing] = useState<Plan | null>(null)
  const invalidate = useInvalidateFinance()
  const { run } = useRunner()
  const canEdit = me.data?.can_manage_plans ?? false
  return (
    <div>
      <PageHeader title="Тарифы и программы"
        description="Условия программ: продолжительность, цена месяца, уроков приоритетного предмета в месяце, срок оплаты. Изменение цены не меняет уже оформленные договоры."
        actions={canEdit ? <Button leftIcon={<Plus className="size-4" />} onClick={() => setCreating(true)}>Новая программа</Button> : undefined} />
      <Loadable query={query} empty={(d) => d.results.length === 0} emptyTitle="Программ пока нет">
        {(data) => (
          <DataTable rows={data.results} getRowKey={(p) => p.id} columns={[
            { key: 'n', header: 'Тариф', render: (p) => <div><p className="font-medium">{p.name}</p><p className="text-xs text-ink-secondary">{p.course_name ?? 'без программы'}</p></div> },
            { key: 's', header: 'Приоритетный предмет', render: (p) => p.subject_name ?? 'все уроки' },
            { key: 'd', header: 'Курс', render: (p) => p.duration_months ? `${p.duration_months} мес. × ${p.current?.lessons_per_package ?? '—'} ур.` : `пакет ${p.current?.lessons_per_package ?? '—'} ур.` },
            { key: 'm', header: 'Месяц', render: (p) => som(p.current?.package_price) },
            { key: 'c', header: 'Стандартная стоимость курса', render: (p) => som(p.current?.standard_course_price) },
            { key: 'dl', header: 'Срок оплаты', render: (p) => `${p.payment_deadline_lessons}-й урок` },
            { key: 'pm', header: 'Оплата', render: (p) => [p.allow_monthly ? 'помесячно' : null, p.allow_full_prepay ? 'предоплата' : null].filter(Boolean).join(', ') },
            { key: 'st', header: 'Статус', render: (p) => <Badge tone={p.is_active ? 'success' : 'muted'}>{p.is_active ? 'Действует' : 'Отключён'}</Badge> },
            { key: 'a', header: '', className: 'text-right', render: (p) => canEdit ? (
              <div className="flex justify-end gap-1">
                <Button size="sm" variant="ghost" onClick={() => setPricing(p)}>Новая цена</Button>
                <Button size="sm" variant="ghost" onClick={async () => {
                  if (await run(() => financeApi.updatePlan(p.id, { is_active: !p.is_active }), p.is_active ? 'Тариф отключён' : 'Тариф включён')) invalidate()
                }}>{p.is_active ? 'Отключить' : 'Включить'}</Button>
              </div>
            ) : null },
          ]} />
        )}
      </Loadable>
      {creating ? <PlanModal onClose={() => setCreating(false)} /> : null}
      {pricing ? <PriceModal plan={pricing} onClose={() => setPricing(null)} /> : null}
    </div>
  )
}

function PlanModal({ onClose }: { onClose: () => void }) {
  const options = useFinanceOptions()
  const invalidate = useInvalidateFinance()
  const { run, busy } = useRunner()
  const [b, setB] = useState({
    name: '', course: '', subject: '', duration_months: '4', lessons_per_package: '12', package_price: '15000',
    payment_deadline_lessons: '3', allow_monthly: true, allow_full_prepay: true, effective_from: today(),
  })
  const set = (patch: Partial<typeof b>) => setB({ ...b, ...patch })
  const course = Number(b.duration_months || 0) * Number(b.package_price || 0)
  return (
    <Modal isOpen onClose={onClose} title="Новая программа" size="lg">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Название тарифа" htmlFor="pl-name" required className="sm:col-span-2">
          <Input id="pl-name" value={b.name} onChange={(e) => set({ name: e.target.value })} placeholder="Kid's Club Standard" />
        </Field>
        <Field label="Программа (курс LMS)" htmlFor="pl-course">
          <Select id="pl-course" value={b.course} placeholder="—" onChange={(e) => set({ course: e.target.value })}
            options={(options.data?.programs ?? []).map((p) => ({ value: String(p.id), label: p.name }))} />
        </Field>
        <Field label="Приоритетный предмет" htmlFor="pl-subject" help="Учебный месяц считается по урокам этого предмета (обычно IT)">
          <Select id="pl-subject" value={b.subject} placeholder="—" onChange={(e) => set({ subject: e.target.value })}
            options={(options.data?.subjects ?? []).map((s) => ({ value: String(s.id), label: s.name }))} />
        </Field>
        <Field label="Учебных месяцев" htmlFor="pl-dur"><Input id="pl-dur" inputMode="numeric" value={b.duration_months} onChange={(e) => set({ duration_months: e.target.value })} /></Field>
        <Field label="Уроков в месяце" htmlFor="pl-les"><Input id="pl-les" inputMode="numeric" value={b.lessons_per_package} onChange={(e) => set({ lessons_per_package: e.target.value })} /></Field>
        <Field label="Цена месяца, сом" htmlFor="pl-price"><Input id="pl-price" inputMode="decimal" value={b.package_price} onChange={(e) => set({ package_price: e.target.value })} /></Field>
        <Field label="Срок оплаты — урок № месяца" htmlFor="pl-dl"><Input id="pl-dl" inputMode="numeric" value={b.payment_deadline_lessons} onChange={(e) => set({ payment_deadline_lessons: e.target.value })} /></Field>
        <Field label="Цена действует с" htmlFor="pl-from"><Input id="pl-from" type="date" value={b.effective_from} onChange={(e) => set({ effective_from: e.target.value })} /></Field>
        <div className="flex flex-col justify-end gap-2 text-sm">
          <label className="flex items-center gap-2"><input type="checkbox" checked={b.allow_monthly} onChange={(e) => set({ allow_monthly: e.target.checked })} />Помесячная оплата</label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={b.allow_full_prepay} onChange={(e) => set({ allow_full_prepay: e.target.checked })} />Предоплата за курс</label>
        </div>
      </div>
      <p className="mt-3 text-sm text-ink-secondary">Стандартная стоимость курса: <b>{som(String(course || 0))}</b></p>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Отмена</Button>
        <Button isLoading={busy} onClick={async () => {
          const ok = await run(() => financeApi.createPlan({
            name: b.name, course: b.course ? Number(b.course) : null, subject: b.subject ? Number(b.subject) : null,
            duration_months: b.duration_months ? Number(b.duration_months) : null, lessons_per_package: Number(b.lessons_per_package),
            package_price: b.package_price, payment_deadline_lessons: Number(b.payment_deadline_lessons),
            allow_monthly: b.allow_monthly, allow_full_prepay: b.allow_full_prepay, effective_from: b.effective_from,
          }), 'Программа создана')
          if (ok) { invalidate(); onClose() }
        }}>Создать</Button>
      </div>
    </Modal>
  )
}

function PriceModal({ plan, onClose }: { plan: Plan; onClose: () => void }) {
  const invalidate = useInvalidateFinance()
  const { run, busy } = useRunner()
  const [price, setPrice] = useState(plan.current?.package_price ?? '')
  const [lessons, setLessons] = useState(String(plan.current?.lessons_per_package ?? 12))
  const [from, setFrom] = useState(today())
  const [reason, setReason] = useState('')
  return (
    <Modal isOpen onClose={onClose} title={`Новая цена: ${plan.name}`}>
      <p className="mb-3 text-sm text-ink-secondary">Действует для новых договоров с указанной даты. Оформленные договоры сохраняют свою стоимость.</p>
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Цена месяца" htmlFor="pv-price"><Input id="pv-price" value={price} onChange={(e) => setPrice(e.target.value)} /></Field>
        <Field label="Уроков в месяце" htmlFor="pv-les"><Input id="pv-les" value={lessons} onChange={(e) => setLessons(e.target.value)} /></Field>
        <Field label="С даты" htmlFor="pv-from"><Input id="pv-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
      </div>
      <Field label="Основание" htmlFor="pv-reason" required className="mt-3"><Textarea id="pv-reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Отмена</Button>
        <Button isLoading={busy} disabled={!reason.trim()} onClick={async () => {
          const ok = await run(() => financeApi.addPlanPrice(plan.id, { package_price: price, lessons_per_package: Number(lessons), effective_from: from, reason }), 'Цена сохранена')
          if (ok) { invalidate(); onClose() }
        }}>Сохранить</Button>
      </div>
    </Modal>
  )
}

// ---------------------------------------------------------------------------
// Журнал операций
// ---------------------------------------------------------------------------

export function AuditPage() {
  const [search, setSearch] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState<number | null>(null)
  const query = useQuery({
    queryKey: [...FINANCE_KEY, 'audit', search, from, to, page],
    queryFn: () => financeApi.audit({ search: search || undefined, date_from: from || undefined, date_to: to || undefined, page }),
    placeholderData: keepPreviousData,
  })
  return (
    <div>
      <PageHeader title="Журнал операций" description="Каждое финансовое действие: кто, когда, что было и что стало, по какой причине. Записи не изменяются и не удаляются." />
      <FilterBar>
        <FilterField size="lg"><SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1) }} placeholder="Действие или причина" /></FilterField>
        <FilterField label="С" htmlFor="au-from"><Input id="au-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></FilterField>
        <FilterField label="По" htmlFor="au-to"><Input id="au-to" type="date" value={to} onChange={(e) => setTo(e.target.value)} /></FilterField>
      </FilterBar>
      <div className="mt-4">
        <Loadable query={query} empty={(d) => d.count === 0} emptyTitle="Записей нет">
          {(data) => (
            <>
              <DataTable rows={data.results} getRowKey={(r) => r.id} onRowClick={(r) => setOpen(open === r.id ? null : r.id)} columns={[
                { key: 't', header: 'Когда', render: (r) => formatDateTime(r.created_at) },
                { key: 'w', header: 'Кто', render: (r) => r.actor },
                { key: 'a', header: 'Действие', render: (r) => (
                  <div><p className="font-medium">{r.action_display}</p><p className="text-xs text-ink-secondary">{r.entity_type} #{r.entity_id}</p>
                    {open === r.id ? (
                      <pre className="mt-2 max-w-xl overflow-x-auto whitespace-pre-wrap rounded bg-surface-muted p-2 text-xs">
                        {`Было: ${JSON.stringify(r.old_values, null, 1)}\nСтало: ${JSON.stringify(r.new_values, null, 1)}`}
                      </pre>
                    ) : null}</div>
                ) },
                { key: 'r', header: 'Причина', render: (r) => r.reason || '—' },
              ]} />
              <div className="mt-3"><Pagination page={page} pageSize={50} totalCount={data.count} onPageChange={setPage} /></div>
            </>
          )}
        </Loadable>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Настройки
// ---------------------------------------------------------------------------

export function SettingsPage() {
  const me = useFinanceMe()
  const query = useQuery({ queryKey: [...FINANCE_KEY, 'settings'], queryFn: financeApi.settings })
  const invalidate = useInvalidateFinance()
  const { run, busy } = useRunner()
  const [form, setForm] = useState<FinanceSettings | null>(null)
  useEffect(() => { if (query.data) setForm(query.data) }, [query.data])
  const readOnly = !(me.data?.can_manage_settings ?? false)
  const set = (patch: Partial<FinanceSettings>) => form && setForm({ ...form, ...patch })
  return (
    <div className="max-w-3xl">
      <PageHeader title="Настройки" description={`Глобальные правила оплаты. Каждое изменение записывается в журнал.${query.data?.updated_at ? ` Изменено ${formatDate(query.data.updated_at)}.` : ''}`} />
      <Loadable query={query}>
        {() => form ? (
          <div className="space-y-4">
            <Card title="Правила">
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Скидка менеджера без согласования, %" htmlFor="st-disc" help="Больше — на согласование бухгалтеру">
                  <Input id="st-disc" disabled={readOnly} value={form.manager_max_discount_percent} onChange={(e) => set({ manager_max_discount_percent: e.target.value })} />
                </Field>
                <Field label="«Скоро оплата» — за N уроков до конца месяца" htmlFor="st-soon">
                  <Input id="st-soon" disabled={readOnly} inputMode="numeric" value={String(form.due_soon_lessons)} onChange={(e) => set({ due_soon_lessons: Number(e.target.value) })} />
                </Field>
                <Field label="Срок оплаты для новых программ — урок №" htmlFor="st-dl">
                  <Input id="st-dl" disabled={readOnly} inputMode="numeric" value={String(form.default_deadline_lessons)} onChange={(e) => set({ default_deadline_lessons: Number(e.target.value) })} />
                </Field>
                <Field label="Возврат без согласования — до, сом" htmlFor="st-ref" help="Пусто — без ограничения">
                  <Input id="st-ref" disabled={readOnly} value={form.accountant_refund_limit ?? ''} onChange={(e) => set({ accountant_refund_limit: e.target.value || null })} />
                </Field>
              </div>
            </Card>
            <Card title="Чек">
              <div className="space-y-3">
                <Field label="Название в чеке" htmlFor="st-name"><Input id="st-name" disabled={readOnly} value={form.academy_name} onChange={(e) => set({ academy_name: e.target.value })} /></Field>
                <Field label="Адрес, телефон, реквизиты" htmlFor="st-det"><Textarea id="st-det" disabled={readOnly} rows={3} value={form.academy_details} onChange={(e) => set({ academy_details: e.target.value })} /></Field>
                <Field label="Подпись внизу чека" htmlFor="st-foot"><Textarea id="st-foot" disabled={readOnly} rows={2} value={form.receipt_footer} onChange={(e) => set({ receipt_footer: e.target.value })} /></Field>
              </div>
            </Card>
            {!readOnly ? (
              <div className="flex justify-end">
                <Button isLoading={busy} onClick={async () => {
                  const { updated_at: _skip, ...body } = form
                  if (await run(() => financeApi.updateSettings(body), 'Настройки сохранены')) invalidate()
                }}>Сохранить</Button>
              </div>
            ) : <p className="text-sm text-ink-secondary">Только просмотр.</p>}
          </div>
        ) : null}
      </Loadable>
    </div>
  )
}
