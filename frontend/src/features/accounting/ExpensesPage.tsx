import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Download, FileText, Paperclip, Plus, RefreshCw } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'

import { accountingApi, newIdempotencyKey } from '@/api/accounting'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Drawer } from '@/components/ui/Drawer'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { StatCard } from '@/components/ui/StatCard'
import { StatGrid } from '@/components/ui/StatGrid'
import { Tabs } from '@/components/ui/Tabs'
import { Textarea } from '@/components/ui/Textarea'
import { Field } from '@/features/worklog/formUi'
import {
  useAccountingMutation,
  useAccountingOptions,
  useExpenseCategories,
  useExpenseOptions,
  useExpenseReport,
  useExpenses,
  useRecurringExpenses,
} from '@/hooks/useAccounting'
import type { Expense, ExpenseCategory, ExpenseFilters, ExpenseOptions, ExpenseStatus, MoneyMethod, RecurringExpense } from '@/types/accounting'

import { HorizontalBars } from './charts'
import { RangePicker, currentMonthKey, rangeLabel, useFinanceRange } from './financeShared'
import { MONTHS, ReasonModal, Section, formatDate, formatDateTime, som, today, useRunner } from './shared'

type Tab = 'list' | 'recurring' | 'report' | 'categories'

const TABS = [
  { key: 'list', label: 'Расходы' },
  { key: 'recurring', label: 'Регулярные' },
  { key: 'report', label: 'Отчёт по категориям' },
  { key: 'categories', label: 'Категории' },
] as const

const STATUS_TONE: Record<ExpenseStatus, BadgeTone> = { UNPAID: 'warning', PAID: 'success', VOID: 'muted' }
const PAGE_SIZE = 50

function StatusBadge({ expense }: { expense: Expense }) {
  if (expense.is_overdue) return <Badge tone="danger">Просрочен</Badge>
  return <Badge tone={STATUS_TONE[expense.status]}>{expense.status_display}</Badge>
}

const ACTION_LABEL: Record<string, string> = {
  expense_create: 'Создан', expense_update: 'Изменён', expense_pay: 'Оплачен', expense_unpay: 'Оплата отменена',
  expense_void: 'Отменён', expense_document: 'Документ прикреплён',
}

/**
 * Расходы компании. Неоплаченный расход — обязательство поставщику, а не
 * потраченные деньги: в денежный поток он попадает только с датой оплаты.
 * Расход не удаляется — отменяется с причиной; изменения — в истории.
 */
export function ExpensesPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = (TABS.some((t) => t.key === searchParams.get('tab')) ? searchParams.get('tab') : 'list') as Tab
  const options = useAccountingOptions()
  const expenseOptions = useExpenseOptions()
  const canEdit = options.data?.can_operate ?? false
  const [creating, setCreating] = useState(false)

  const setTab = (key: Tab) => {
    const next = new URLSearchParams(searchParams)
    next.set('tab', key)
    next.delete('status')
    next.delete('expense')
    setSearchParams(next, { replace: true })
  }

  return (
    <div>
      <PageHeader
        title="Расходы компании"
        description="Аренда, коммунальные услуги, связь, материалы, оборудование, реклама и другие расходы. Не оплаченный расход — обязательство, а не потраченные деньги."
        actions={canEdit && expenseOptions.data ? (
          <Button leftIcon={<Plus className="size-4" />} onClick={() => setCreating(true)}>Добавить расход</Button>
        ) : null}
      />
      <Tabs aria-label="Разделы расходов" items={TABS} value={tab} onChange={setTab} />

      {expenseOptions.isLoading ? <LoadingState /> : expenseOptions.isError || !expenseOptions.data ? (
        <ErrorState onRetry={() => expenseOptions.refetch()} />
      ) : (
        <>
          {tab === 'list' ? <ExpenseList options={expenseOptions.data} canEdit={canEdit} /> : null}
          {tab === 'recurring' ? <RecurringTab options={expenseOptions.data} canEdit={canEdit} /> : null}
          {tab === 'report' ? <ReportTab /> : null}
          {tab === 'categories' ? <CategoriesTab canEdit={canEdit} /> : null}
        </>
      )}

      {creating && expenseOptions.data ? (
        <ExpenseFormModal options={expenseOptions.data} onClose={() => setCreating(false)} />
      ) : null}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Список
// ---------------------------------------------------------------------------

function ExpenseList({ options, canEdit }: { options: ExpenseOptions; canEdit: boolean }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const initialStatus = searchParams.get('status') as ExpenseStatus | null
  const [filters, setFilters] = useState<ExpenseFilters>({ status: initialStatus ?? undefined, page: 1 })
  const set = (patch: Partial<ExpenseFilters>) => setFilters({ ...filters, ...patch, page: patch.page ?? 1 })
  const list = useExpenses({ ...filters, page_size: PAGE_SIZE })
  const openId = Number(searchParams.get('expense')) || null
  const open = (id: number | null) => {
    const next = new URLSearchParams(searchParams)
    if (id) next.set('expense', String(id))
    else next.delete('expense')
    setSearchParams(next, { replace: true })
  }
  const { run, busy } = useRunner()
  const range = filters.date_from && filters.date_to ? { date_from: filters.date_from, date_to: filters.date_to } : { month: currentMonthKey() }

  return (
    <>
      <StatGrid>
        <StatCard label="К оплате поставщикам" value={som(options.unpaid.amount)} hint={`${options.unpaid.count} расходов`}
          tone={Number(options.unpaid.amount) > 0 ? 'warning' : 'default'} />
        <StatCard label="Просрочено" value={som(options.unpaid.overdue_amount)} hint={`${options.unpaid.overdue_count} расходов`}
          tone={Number(options.unpaid.overdue_amount) > 0 ? 'danger' : 'default'} />
        {list.data ? <StatCard label="По фильтру: оплачено" value={som(list.data.totals.paid)} hint={`не оплачено ${som(list.data.totals.unpaid)}`} /> : null}
      </StatGrid>

      <div className="mt-6">
        <FilterBar>
          <FilterField size="lg">
            <SearchInput aria-label="Поиск расходов" placeholder="Описание, получатель, № документа" value={filters.search ?? ''}
              onChange={(value) => set({ search: value || undefined })} />
          </FilterField>
          <FilterField>
            <Select aria-label="Категория" value={filters.category ? String(filters.category) : ''} placeholder="Все категории"
              options={options.categories.map((c) => ({ value: String(c.id), label: c.name }))}
              onChange={(e) => set({ category: Number(e.target.value) || undefined })} />
          </FilterField>
          <FilterField>
            <Select aria-label="Статус" value={filters.status ?? ''} placeholder="Оплаченные и нет"
              options={options.statuses.map((s) => ({ value: s.value, label: s.label }))}
              onChange={(e) => set({ status: (e.target.value || undefined) as ExpenseStatus | undefined })} />
          </FilterField>
          <FilterField>
            <Select aria-label="Способ оплаты" value={filters.payment_method ?? ''} placeholder="Все способы"
              options={options.payment_methods.map((m) => ({ value: m.value, label: m.label }))}
              onChange={(e) => set({ payment_method: (e.target.value || undefined) as MoneyMethod | undefined })} />
          </FilterField>
          <FilterField>
            <Select aria-label="Ответственный" value={filters.responsible ? String(filters.responsible) : ''} placeholder="Все ответственные"
              options={options.staff.map((u) => ({ value: String(u.id), label: u.name }))}
              onChange={(e) => set({ responsible: Number(e.target.value) || undefined })} />
          </FilterField>
          <FilterField label="Дата расхода с" htmlFor="ex-from">
            <Input id="ex-from" type="date" value={filters.date_from ?? ''} onChange={(e) => set({ date_from: e.target.value || undefined })} />
          </FilterField>
          <FilterField label="по" htmlFor="ex-to">
            <Input id="ex-to" type="date" value={filters.date_to ?? ''} onChange={(e) => set({ date_to: e.target.value || undefined })} />
          </FilterField>
          <FilterField>
            <label className="flex h-10 items-center gap-2 text-sm text-ink-secondary">
              <input type="checkbox" checked={Boolean(filters.overdue)} onChange={(e) => set({ overdue: e.target.checked || undefined })} />
              Только просроченные
            </label>
          </FilterField>
          <FilterField>
            <Button variant="secondary" leftIcon={<Download className="size-4" />} isLoading={busy}
              onClick={() => run(() => accountingApi.downloadExpenses(range, { ...filters, page: undefined }))}>
              Excel
            </Button>
          </FilterField>
        </FilterBar>

        {list.isLoading ? <LoadingState /> : list.isError || !list.data ? <ErrorState onRetry={() => list.refetch()} /> :
          list.data.results.length === 0 ? <EmptyState title="Расходов не найдено" description="Измените фильтры или добавьте расход." /> : (
            <div className="card overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr><th>Дата</th><th>Категория</th><th>Описание</th><th>Получатель</th><th className="text-right">Сумма</th><th>Статус</th><th>Оплачен</th><th /></tr>
                </thead>
                <tbody>
                  {list.data.results.map((e) => (
                    <tr key={e.id}>
                      <td className="whitespace-nowrap">{formatDate(e.expense_date)}</td>
                      <td className="text-sm">{e.category_name}</td>
                      <td className="max-w-xs">
                        <span className="font-medium text-ink">{e.description}</span>
                        {e.has_document ? <Paperclip className="ml-1 inline size-3.5 text-ink-muted" aria-label="есть документ" /> : null}
                        {e.recurring ? <RefreshCw className="ml-1 inline size-3.5 text-ink-muted" aria-label="регулярный" /> : null}
                      </td>
                      <td className="text-sm">{e.vendor || '—'}</td>
                      <td className="whitespace-nowrap text-right tabular-nums">{som(e.amount)}</td>
                      <td><StatusBadge expense={e} /></td>
                      <td className="whitespace-nowrap text-sm">{e.paid_date ? formatDate(e.paid_date) : e.due_date ? `до ${formatDate(e.due_date)}` : '—'}</td>
                      <td className="text-right"><Button size="sm" variant="ghost" onClick={() => open(e.id)}>Открыть</Button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        {list.data ? (
          <Pagination page={filters.page ?? 1} pageSize={PAGE_SIZE} totalCount={list.data.count} onPageChange={(page) => set({ page })} />
        ) : null}
      </div>

      {openId ? <ExpenseDrawer id={openId} options={options} canEdit={canEdit} onClose={() => open(null)} /> : null}
    </>
  )
}

// ---------------------------------------------------------------------------
// Карточка расхода
// ---------------------------------------------------------------------------

function ExpenseDrawer({ id, options, canEdit, onClose }: { id: number; options: ExpenseOptions; canEdit: boolean; onClose: () => void }) {
  const detail = useQuery({ queryKey: ['accounting', 'expenses', 'detail', id], queryFn: () => accountingApi.expense(id) })
  const history = useQuery({ queryKey: ['accounting', 'expenses', 'history', id], queryFn: () => accountingApi.expenseHistory(id) })
  const [mode, setMode] = useState<null | 'edit' | 'pay' | 'unpay' | 'void'>(null)
  const { run, busy } = useRunner()
  const mutate = useAccountingMutation(async (fn: () => Promise<unknown>) => fn())
  const e = detail.data

  return (
    <Drawer isOpen onClose={onClose} title={e ? e.description : 'Расход'} side="right" size="lg">
      {detail.isLoading ? <LoadingState /> : detail.isError || !e ? <ErrorState onRetry={() => detail.refetch()} /> : (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge expense={e} />
            <span className="text-xl font-semibold tabular-nums text-ink">{som(e.amount)}</span>
          </div>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <dt className="text-ink-secondary">Категория</dt><dd>{e.category_name}</dd>
            <dt className="text-ink-secondary">Дата расхода</dt><dd>{formatDate(e.expense_date)}</dd>
            <dt className="text-ink-secondary">Оплатить до</dt><dd>{formatDate(e.due_date)}</dd>
            <dt className="text-ink-secondary">Дата оплаты</dt><dd>{e.paid_date ? formatDate(e.paid_date) : 'не оплачен'}</dd>
            <dt className="text-ink-secondary">Получатель</dt><dd>{e.vendor || '—'}</dd>
            <dt className="text-ink-secondary">Способ оплаты</dt><dd>{e.payment_method_display}</dd>
            <dt className="text-ink-secondary">Ответственный</dt><dd>{e.responsible_name || '—'}</dd>
            <dt className="text-ink-secondary">Документ №</dt><dd>{e.reference || '—'}</dd>
            {e.recurring ? (<><dt className="text-ink-secondary">Регулярный</dt><dd>{e.recurring_description}</dd></>) : null}
            <dt className="text-ink-secondary">Внёс</dt><dd>{e.created_by_name} · {formatDateTime(e.created_at)}</dd>
            {e.status === 'VOID' ? (<><dt className="text-ink-secondary">Отменён</dt><dd>{e.voided_by_name} · {e.void_reason}</dd></>) : null}
          </dl>
          {e.comment ? <p className="whitespace-pre-line text-sm text-ink-secondary">{e.comment}</p> : null}

          <div className="flex flex-wrap items-center gap-2">
            {e.has_document ? (
              <Button size="sm" variant="secondary" leftIcon={<FileText className="size-4" />} isLoading={busy}
                onClick={() => run(() => accountingApi.downloadExpenseDocument(e.id, e.document_name))}>
                {e.document_name || 'Документ'}
              </Button>
            ) : <span className="text-sm text-ink-muted">Документ не прикреплён</span>}
            {canEdit && e.status !== 'VOID' ? (
              <label className="inline-flex cursor-pointer items-center gap-1.5 text-sm font-medium text-brand-700 hover:underline">
                <Paperclip className="size-4" aria-hidden />{e.has_document ? 'Заменить' : 'Прикрепить'}
                <input type="file" className="sr-only" accept=".pdf,.jpg,.jpeg,.png,.webp,.heic,.xlsx,.xls,.docx,.doc"
                  onChange={(ev) => {
                    const file = ev.target.files?.[0]
                    if (file) void run(() => mutate.mutateAsync(() => accountingApi.uploadExpenseDocument(e.id, file, e.version)), 'Документ прикреплён')
                  }} />
              </label>
            ) : null}
          </div>

          {canEdit && e.status !== 'VOID' ? (
            <div className="flex flex-wrap gap-2">
              {e.status === 'UNPAID' ? <Button onClick={() => setMode('pay')}>Отметить оплату</Button> : null}
              {e.status === 'PAID' ? <Button variant="secondary" onClick={() => setMode('unpay')}>Отменить оплату</Button> : null}
              <Button variant="secondary" onClick={() => setMode('edit')}>Изменить</Button>
              <Button variant="danger" onClick={() => setMode('void')}>Отменить расход</Button>
            </div>
          ) : null}

          <section>
            <h3 className="mb-2 text-sm font-semibold text-ink">История изменений</h3>
            {history.data?.results.length ? (
              <ul className="space-y-2 text-sm">
                {history.data.results.map((h) => (
                  <li key={h.id} className="rounded-lg border border-border p-2">
                    <p className="font-medium text-ink">{ACTION_LABEL[h.action] ?? h.action}</p>
                    <p className="text-xs text-ink-secondary">{h.actor_name} · {formatDateTime(h.created_at)}</p>
                    {h.reason ? <p className="text-xs text-ink-secondary">Причина: {h.reason}</p> : null}
                    <ChangedFields old={h.old_values} next={h.new_values} />
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-ink-muted">Нет записей</p>}
          </section>
        </div>
      )}

      {e && mode === 'edit' ? <ExpenseFormModal options={options} expense={e} onClose={() => setMode(null)} /> : null}
      {e && mode === 'pay' ? <PayModal expense={e} options={options} onClose={() => setMode(null)} /> : null}
      {e ? (
        <ReasonModal isOpen={mode === 'unpay'} title="Отменить отметку об оплате"
          description="Расход вернётся в «не оплачен» и уйдёт из движения денег. Используйте, если оплата не состоялась или дата указана неверно."
          confirmLabel="Отменить оплату" onClose={() => setMode(null)}
          onConfirm={(reason) => run(() => mutate.mutateAsync(() => accountingApi.unpayExpense(e.id, reason, e.version)), 'Оплата отменена')} />
      ) : null}
      {e ? (
        <ReasonModal isOpen={mode === 'void'} title="Отменить расход" tone="danger"
          description="Расход перестанет учитываться в отчётах. Запись и история останутся — удалить расход нельзя."
          confirmLabel="Отменить расход" onClose={() => setMode(null)}
          onConfirm={(reason) => run(() => mutate.mutateAsync(() => accountingApi.voidExpense(e.id, reason, e.version)), 'Расход отменён')} />
      ) : null}
    </Drawer>
  )
}

const FIELD_LABEL: Record<string, string> = {
  category_id: 'Категория', description: 'Описание', amount: 'Сумма', expense_date: 'Дата расхода', due_date: 'Оплатить до',
  vendor: 'Получатель', payment_method: 'Способ', responsible_id: 'Ответственный', reference: 'Документ №', comment: 'Комментарий',
  status: 'Статус', paid_date: 'Дата оплаты', document_name: 'Документ',
}

function ChangedFields({ old, next }: { old: Record<string, unknown>; next: Record<string, unknown> }) {
  const keys = Object.keys(next).filter((k) => Object.keys(old).length && JSON.stringify(old[k]) !== JSON.stringify(next[k]))
  if (!keys.length) return null
  return (
    <ul className="mt-1 text-xs text-ink-secondary">
      {keys.map((k) => (
        <li key={k}>{FIELD_LABEL[k] ?? k}: {String(old[k] ?? '—')} → {String(next[k] ?? '—')}</li>
      ))}
    </ul>
  )
}

function PayModal({ expense, options, onClose }: { expense: Expense; options: ExpenseOptions; onClose: () => void }) {
  const [form, setForm] = useState({ paid_date: today(), payment_method: expense.payment_method as string, reference: expense.reference })
  const { run, busy } = useRunner()
  const mutate = useAccountingMutation(async (fn: () => Promise<unknown>) => fn())
  return (
    <Modal isOpen onClose={onClose} title={`Оплата: ${expense.description}`}>
      <p className="mb-3 text-sm text-ink-secondary">
        Сумма {som(expense.amount)} попадёт в движение денег датой оплаты. Повторно отметить оплату нельзя.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Дата оплаты" required htmlFor="pay-date">
          <Input id="pay-date" type="date" max={today()} value={form.paid_date} onChange={(e) => setForm({ ...form, paid_date: e.target.value })} />
        </Field>
        <Field label="Способ оплаты" htmlFor="pay-method">
          <Select id="pay-method" value={form.payment_method} options={options.payment_methods.map((m) => ({ value: m.value, label: m.label }))}
            onChange={(e) => setForm({ ...form, payment_method: e.target.value })} />
        </Field>
        <Field label="Номер платёжного документа" htmlFor="pay-ref" className="sm:col-span-2">
          <Input id="pay-ref" value={form.reference} onChange={(e) => setForm({ ...form, reference: e.target.value })} />
        </Field>
      </div>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Отмена</Button>
        <Button isLoading={busy} disabled={!form.paid_date} onClick={async () => {
          const ok = await run(() => mutate.mutateAsync(() => accountingApi.payExpense(expense.id, { ...form, version: expense.version })), 'Оплата отмечена')
          if (ok) onClose()
        }}>Отметить оплату</Button>
      </div>
    </Modal>
  )
}

// ---------------------------------------------------------------------------
// Форма расхода
// ---------------------------------------------------------------------------

function ExpenseFormModal({ options, expense, onClose }: { options: ExpenseOptions; expense?: Expense; onClose: () => void }) {
  const active = options.categories.filter((c) => c.is_active || c.id === expense?.category)
  const [form, setForm] = useState({
    category: expense ? String(expense.category) : '',
    description: expense?.description ?? '',
    amount: expense?.amount ?? '',
    expense_date: expense?.expense_date ?? today(),
    due_date: expense?.due_date ?? '',
    vendor: expense?.vendor ?? '',
    payment_method: (expense?.payment_method ?? 'cash') as string,
    responsible: expense?.responsible ? String(expense.responsible) : '',
    reference: expense?.reference ?? '',
    comment: expense?.comment ?? '',
    paid: false,
    paid_date: today(),
    reason: '',
  })
  const [file, setFile] = useState<File | null>(null)
  const [key] = useState(newIdempotencyKey)
  const { run, busy } = useRunner()
  const mutate = useAccountingMutation(async (fn: () => Promise<unknown>) => fn())
  const paidEdit = expense?.status === 'PAID'
  const valid = Boolean(form.category && form.description.trim() && Number(form.amount) > 0 && form.expense_date)
    && (!paidEdit || form.reason.trim())
  const body = {
    category: Number(form.category), description: form.description.trim(), amount: form.amount,
    expense_date: form.expense_date, due_date: form.due_date || null, vendor: form.vendor.trim(),
    payment_method: form.payment_method as MoneyMethod, responsible: form.responsible ? Number(form.responsible) : null,
    reference: form.reference.trim(), comment: form.comment,
  }

  const submit = async () => {
    const ok = await run(() => mutate.mutateAsync(() => expense
      ? accountingApi.updateExpense(expense.id, { ...body, version: expense.version, reason: form.reason.trim() })
      : accountingApi.createExpense({ ...body, paid: form.paid, paid_date: form.paid ? form.paid_date : null, document: file }, key)),
    expense ? 'Расход изменён' : 'Расход добавлен')
    if (ok) onClose()
  }

  return (
    <Modal isOpen onClose={onClose} title={expense ? 'Изменить расход' : 'Новый расход'} size="lg">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Категория" required htmlFor="ex-cat">
          <Select id="ex-cat" value={form.category} placeholder="Выберите категорию"
            options={active.map((c) => ({ value: String(c.id), label: c.name }))}
            onChange={(e) => setForm({ ...form, category: e.target.value })} />
        </Field>
        <Field label="Сумма, сом" required htmlFor="ex-amount">
          <Input id="ex-amount" type="number" min="0.01" step="0.01" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
        </Field>
        <Field label="Описание" required htmlFor="ex-desc" className="sm:col-span-2">
          <Input id="ex-desc" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </Field>
        <Field label="Дата расхода" required htmlFor="ex-date" help="Дата документа — к какому периоду относится расход.">
          <Input id="ex-date" type="date" value={form.expense_date} onChange={(e) => setForm({ ...form, expense_date: e.target.value })} />
        </Field>
        <Field label="Оплатить до" htmlFor="ex-due">
          <Input id="ex-due" type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
        </Field>
        <Field label="Получатель / поставщик" htmlFor="ex-vendor">
          <Input id="ex-vendor" value={form.vendor} onChange={(e) => setForm({ ...form, vendor: e.target.value })} />
        </Field>
        <Field label="Номер документа" htmlFor="ex-ref" help="Один и тот же документ получателя не проводится дважды.">
          <Input id="ex-ref" value={form.reference} onChange={(e) => setForm({ ...form, reference: e.target.value })} />
        </Field>
        <Field label="Способ оплаты" htmlFor="ex-method">
          <Select id="ex-method" value={form.payment_method} options={options.payment_methods.map((m) => ({ value: m.value, label: m.label }))}
            onChange={(e) => setForm({ ...form, payment_method: e.target.value })} />
        </Field>
        <Field label="Ответственный сотрудник" htmlFor="ex-resp">
          <Select id="ex-resp" value={form.responsible} placeholder="Не указан"
            options={options.staff.map((u) => ({ value: String(u.id), label: u.name }))}
            onChange={(e) => setForm({ ...form, responsible: e.target.value })} />
        </Field>
        <Field label="Комментарий" htmlFor="ex-comment" className="sm:col-span-2">
          <Textarea id="ex-comment" rows={2} value={form.comment} onChange={(e) => setForm({ ...form, comment: e.target.value })} />
        </Field>
        {!expense ? (
          <>
            <Field label="Подтверждающий документ" htmlFor="ex-file" help="PDF, фото, Excel или Word, до 10 МБ.">
              <input id="ex-file" type="file" className="text-sm" accept=".pdf,.jpg,.jpeg,.png,.webp,.heic,.xlsx,.xls,.docx,.doc"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            </Field>
            <div className="space-y-2">
              <label className="flex items-center gap-2 text-sm text-ink">
                <input type="checkbox" checked={form.paid} onChange={(e) => setForm({ ...form, paid: e.target.checked })} />
                Уже оплачен
              </label>
              {form.paid ? (
                <Input aria-label="Дата оплаты" type="date" max={today()} value={form.paid_date}
                  onChange={(e) => setForm({ ...form, paid_date: e.target.value })} />
              ) : <p className="text-xs text-ink-secondary">Без отметки расход сохранится как «не оплачен» — это обязательство, не потраченные деньги.</p>}
            </div>
          </>
        ) : null}
        {paidEdit ? (
          <Field label="Причина изменения" required htmlFor="ex-reason" className="sm:col-span-2"
            help="Расход уже оплачен: изменение суммы, категории, способа или даты меняет отчёты о потраченных деньгах.">
            <Textarea id="ex-reason" rows={2} value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
          </Field>
        ) : null}
      </div>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Отмена</Button>
        <Button disabled={!valid} isLoading={busy} onClick={submit}>{expense ? 'Сохранить' : 'Добавить'}</Button>
      </div>
    </Modal>
  )
}

// ---------------------------------------------------------------------------
// Регулярные расходы
// ---------------------------------------------------------------------------

function RecurringTab({ options, canEdit }: { options: ExpenseOptions; canEdit: boolean }) {
  const recurring = useRecurringExpenses()
  const [editing, setEditing] = useState<RecurringExpense | 'new' | null>(null)
  const [month, setMonth] = useState(currentMonthKey())
  const { run, busy } = useRunner()
  const mutate = useAccountingMutation(async (fn: () => Promise<unknown>) => fn())

  const generate = () => {
    const [y, m] = month.split('-').map(Number)
    return run(() => mutate.mutateAsync(() => accountingApi.generateRecurringExpenses(y, m)),
      `Расходы за ${MONTHS[m - 1].toLowerCase()} ${y} созданы (повторно не дублируются)`)
  }

  return (
    <>
      <p className="mb-4 text-sm text-ink-secondary">
        Шаблон — не деньги: раз в месяц по нему создаётся один неоплаченный расход (автоматически при ежедневном запуске
        задач или кнопкой ниже). Повторный запуск за тот же месяц ничего не дублирует; оплату отмечают у созданного расхода.
      </p>
      {canEdit ? (
        <FilterBar>
          <FilterField label="Месяц" htmlFor="rec-month">
            <Input id="rec-month" type="month" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)} />
          </FilterField>
          <FilterField>
            <Button variant="secondary" isLoading={busy} onClick={generate}>Создать расходы за месяц</Button>
          </FilterField>
          <FilterField>
            <Button leftIcon={<Plus className="size-4" />} onClick={() => setEditing('new')}>Новый регулярный расход</Button>
          </FilterField>
        </FilterBar>
      ) : null}
      {recurring.isLoading ? <LoadingState /> : recurring.isError ? <ErrorState onRetry={() => recurring.refetch()} /> :
        !recurring.data?.length ? <EmptyState title="Регулярных расходов нет" description="Например, аренда, интернет, связь." /> : (
          <div className="card overflow-x-auto">
            <table className="data-table">
              <thead><tr><th>Описание</th><th>Категория</th><th className="text-right">Сумма в месяц</th><th>Число</th><th>Действует</th><th>Создано расходов</th><th /></tr></thead>
              <tbody>
                {recurring.data.map((r) => (
                  <tr key={r.id}>
                    <td className="font-medium text-ink">{r.description}{r.vendor ? <span className="block text-xs text-ink-secondary">{r.vendor}</span> : null}</td>
                    <td className="text-sm">{r.category_name}</td>
                    <td className="text-right tabular-nums">{som(r.amount)}</td>
                    <td>{r.day_of_month}</td>
                    <td className="whitespace-nowrap text-sm">
                      {r.is_active ? null : <Badge className="mr-1">остановлен</Badge>}
                      с {formatDate(r.start_month).slice(3)}{r.end_month ? ` по ${formatDate(r.end_month).slice(3)}` : ''}
                    </td>
                    <td className="text-sm">{r.expenses_count ?? 0}{r.last_month ? ` · последний ${formatDate(r.last_month).slice(3)}` : ''}</td>
                    <td className="text-right">{canEdit ? <Button size="sm" variant="ghost" onClick={() => setEditing(r)}>Изменить</Button> : null}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      {editing ? <RecurringModal options={options} recurring={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)} /> : null}
    </>
  )
}

function RecurringModal({ options, recurring, onClose }: { options: ExpenseOptions; recurring?: RecurringExpense; onClose: () => void }) {
  const [form, setForm] = useState({
    category: recurring ? String(recurring.category) : '',
    description: recurring?.description ?? '',
    amount: recurring?.amount ?? '',
    vendor: recurring?.vendor ?? '',
    payment_method: (recurring?.payment_method ?? 'bank') as string,
    responsible: recurring?.responsible ? String(recurring.responsible) : '',
    day_of_month: String(recurring?.day_of_month ?? 1),
    start_month: (recurring?.start_month ?? `${currentMonthKey()}-01`).slice(0, 7),
    end_month: recurring?.end_month?.slice(0, 7) ?? '',
    is_active: recurring?.is_active ?? true,
    comment: recurring?.comment ?? '',
  })
  const { run, busy } = useRunner()
  const mutate = useAccountingMutation(async (fn: () => Promise<unknown>) => fn())
  const day = Number(form.day_of_month)
  const valid = Boolean(form.category && form.description.trim() && Number(form.amount) > 0 && day >= 1 && day <= 28 && form.start_month)
  const submit = async () => {
    const body = {
      category: Number(form.category), description: form.description.trim(), amount: form.amount, vendor: form.vendor.trim(),
      payment_method: form.payment_method, responsible: form.responsible ? Number(form.responsible) : null, day_of_month: day,
      start_month: `${form.start_month}-01`, end_month: form.end_month ? `${form.end_month}-01` : null,
      is_active: form.is_active, comment: form.comment,
    }
    const ok = await run(() => mutate.mutateAsync(() => recurring
      ? accountingApi.updateRecurringExpense(recurring.id, body)
      : accountingApi.createRecurringExpense(body)), 'Регулярный расход сохранён')
    if (ok) onClose()
  }
  return (
    <Modal isOpen onClose={onClose} title={recurring ? 'Регулярный расход' : 'Новый регулярный расход'} size="lg">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Категория" required htmlFor="rc-cat">
          <Select id="rc-cat" value={form.category} placeholder="Выберите категорию"
            options={options.categories.filter((c) => c.is_active || String(c.id) === form.category).map((c) => ({ value: String(c.id), label: c.name }))}
            onChange={(e) => setForm({ ...form, category: e.target.value })} />
        </Field>
        <Field label="Сумма в месяц, сом" required htmlFor="rc-amount">
          <Input id="rc-amount" type="number" min="0.01" step="0.01" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
        </Field>
        <Field label="Описание" required htmlFor="rc-desc" className="sm:col-span-2">
          <Input id="rc-desc" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </Field>
        <Field label="Получатель" htmlFor="rc-vendor">
          <Input id="rc-vendor" value={form.vendor} onChange={(e) => setForm({ ...form, vendor: e.target.value })} />
        </Field>
        <Field label="Способ оплаты" htmlFor="rc-method">
          <Select id="rc-method" value={form.payment_method} options={options.payment_methods.map((m) => ({ value: m.value, label: m.label }))}
            onChange={(e) => setForm({ ...form, payment_method: e.target.value })} />
        </Field>
        <Field label="Ответственный" htmlFor="rc-resp">
          <Select id="rc-resp" value={form.responsible} placeholder="Не указан" options={options.staff.map((u) => ({ value: String(u.id), label: u.name }))}
            onChange={(e) => setForm({ ...form, responsible: e.target.value })} />
        </Field>
        <Field label="Число месяца (1–28)" required htmlFor="rc-day" help="Дата расхода и срок оплаты.">
          <Input id="rc-day" type="number" min="1" max="28" value={form.day_of_month} onChange={(e) => setForm({ ...form, day_of_month: e.target.value })} />
        </Field>
        <Field label="С месяца" required htmlFor="rc-start">
          <Input id="rc-start" type="month" value={form.start_month} onChange={(e) => setForm({ ...form, start_month: e.target.value })} />
        </Field>
        <Field label="По месяц (включительно)" htmlFor="rc-end">
          <Input id="rc-end" type="month" value={form.end_month} onChange={(e) => setForm({ ...form, end_month: e.target.value })} />
        </Field>
        <label className="flex items-center gap-2 text-sm text-ink sm:col-span-2">
          <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
          Действует (снимите, чтобы остановить; созданные расходы останутся)
        </label>
        <Field label="Комментарий" htmlFor="rc-comment" className="sm:col-span-2">
          <Textarea id="rc-comment" rows={2} value={form.comment} onChange={(e) => setForm({ ...form, comment: e.target.value })} />
        </Field>
      </div>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Отмена</Button>
        <Button disabled={!valid} isLoading={busy} onClick={submit}>Сохранить</Button>
      </div>
    </Modal>
  )
}

// ---------------------------------------------------------------------------
// Отчёт и категории
// ---------------------------------------------------------------------------

function ReportTab() {
  const range = useFinanceRange()
  const report = useExpenseReport(range.params)
  const { run, busy } = useRunner()
  const d = report.data
  return (
    <>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-2">
        <RangePicker value={range.choice} onChange={range.setChoice} />
        <Button variant="secondary" leftIcon={<Download className="size-4" />} isLoading={busy}
          onClick={() => run(() => accountingApi.downloadExpenses(range.params))}>Excel</Button>
      </div>
      {report.isLoading ? <LoadingState /> : report.isError || !d ? <ErrorState onRetry={() => report.refetch()} /> : (
        <>
          <p className="mb-3 text-sm text-ink-secondary">{rangeLabel(d.date_from, d.date_to)}</p>
          <StatGrid>
            <StatCard label="Оплачено (потрачено)" value={som(d.paid)} hint={d.definitions.paid} />
            <StatCard label="Начислено по дате расхода" value={som(d.incurred)} hint={d.definitions.incurred} />
            <StatCard label="Не оплачено из начисленного" value={som(d.unpaid)} tone={Number(d.unpaid) > 0 ? 'warning' : 'default'} hint={d.definitions.unpaid} />
          </StatGrid>
          <div className="mt-6 grid gap-4 lg:grid-cols-2">
            <HorizontalBars title="Оплачено по категориям"
              rows={d.by_category.filter((r) => Number(r.paid) > 0).map((r) => ({ label: r.category_name, value: Number(r.paid) }))} />
            <div className="card overflow-x-auto">
              <table className="data-table">
                <thead><tr><th>Месяц</th><th className="text-right">Оплачено</th><th className="text-right">Начислено</th></tr></thead>
                <tbody>
                  {d.by_month.map((m) => (
                    <tr key={`${m.year}-${m.month}`}>
                      <td>{MONTHS[m.month - 1]} {m.year}</td>
                      <td className="text-right tabular-nums">{som(m.paid)}</td>
                      <td className="text-right tabular-nums">{som(m.incurred)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <Section title="По категориям">
            {d.by_category.length === 0 ? <EmptyState title="Расходов за период нет" /> : (
              <div className="card overflow-x-auto">
                <table className="data-table">
                  <thead><tr><th>Категория</th><th className="text-right">Оплачено</th><th className="text-right">Доля</th><th className="text-right">Операций</th><th className="text-right">Начислено</th><th className="text-right">Не оплачено</th></tr></thead>
                  <tbody>
                    {d.by_category.map((r) => (
                      <tr key={r.category}>
                        <td className="font-medium text-ink">{r.category_name}</td>
                        <td className="text-right tabular-nums">{som(r.paid)}</td>
                        <td className="text-right tabular-nums">{r.share_percent !== null ? `${Number(r.share_percent)}%` : '—'}</td>
                        <td className="text-right">{r.paid_count}</td>
                        <td className="text-right tabular-nums">{som(r.incurred)}</td>
                        <td className="text-right tabular-nums">{som(r.unpaid)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>
        </>
      )}
    </>
  )
}

function CategoriesTab({ canEdit }: { canEdit: boolean }) {
  const categories = useExpenseCategories()
  const [editing, setEditing] = useState<ExpenseCategory | 'new' | null>(null)
  const { run } = useRunner()
  const mutate = useAccountingMutation(async (fn: () => Promise<unknown>) => fn())
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-ink-secondary">Категорию нельзя удалить — её отключают; у старых расходов она остаётся.</p>
        {canEdit ? <Button leftIcon={<Plus className="size-4" />} onClick={() => setEditing('new')}>Новая категория</Button> : null}
      </div>
      {categories.isLoading ? <LoadingState /> : categories.isError ? <ErrorState onRetry={() => categories.refetch()} /> : (
        <div className="card overflow-x-auto">
          <table className="data-table">
            <thead><tr><th>Категория</th><th>Описание</th><th className="text-right">Расходов</th><th>Статус</th><th /></tr></thead>
            <tbody>
              {categories.data?.map((c) => (
                <tr key={c.id}>
                  <td className="font-medium text-ink">{c.name}</td>
                  <td className="text-sm">{c.description || '—'}</td>
                  <td className="text-right">{c.expenses_count ?? 0}</td>
                  <td>{c.is_active ? <Badge tone="success">используется</Badge> : <Badge>отключена</Badge>}</td>
                  <td className="whitespace-nowrap text-right">
                    {canEdit ? (
                      <>
                        <Button size="sm" variant="ghost" onClick={() => setEditing(c)}>Изменить</Button>
                        <Button size="sm" variant="ghost" onClick={() => run(() => mutate.mutateAsync(() =>
                          accountingApi.updateExpenseCategory(c.id, { is_active: !c.is_active })), c.is_active ? 'Категория отключена' : 'Категория включена')}>
                          {c.is_active ? 'Отключить' : 'Включить'}
                        </Button>
                      </>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editing ? <CategoryModal category={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)} /> : null}
    </>
  )
}

function CategoryModal({ category, onClose }: { category?: ExpenseCategory; onClose: () => void }) {
  const [form, setForm] = useState({ name: category?.name ?? '', description: category?.description ?? '' })
  const { run, busy } = useRunner()
  const mutate = useAccountingMutation(async (fn: () => Promise<unknown>) => fn())
  return (
    <Modal isOpen onClose={onClose} title={category ? 'Категория расходов' : 'Новая категория'}>
      <Field label="Название" required htmlFor="cat-name">
        <Input id="cat-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
      </Field>
      <Field label="Описание" htmlFor="cat-desc" className="mt-3">
        <Input id="cat-desc" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
      </Field>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Отмена</Button>
        <Button disabled={!form.name.trim()} isLoading={busy} onClick={async () => {
          const body = { name: form.name.trim(), description: form.description.trim() }
          const ok = await run(() => mutate.mutateAsync(() => category
            ? accountingApi.updateExpenseCategory(category.id, body)
            : accountingApi.createExpenseCategory(body)), 'Категория сохранена')
          if (ok) onClose()
        }}>Сохранить</Button>
      </div>
    </Modal>
  )
}
