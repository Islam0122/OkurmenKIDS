import { useState } from 'react'
import type { ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'

import { financeApi } from '@/api/finance'
import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { Field } from '@/features/worklog/formUi'
import { som, useRunner } from '@/features/accounting/shared'
import type { ContractStatus, FinanceOptions, InvoiceStatus, PaymentStage, QueueFilters, QueueRow } from '@/types/finance'
import { cn } from '@/utils/cn'

export { formatDate, formatDateTime, som, today, useRunner } from '@/features/accounting/shared'

export const FINANCE_KEY = ['finance'] as const

export function useFinanceMe() {
  return useQuery({ queryKey: [...FINANCE_KEY, 'me'], queryFn: financeApi.me, staleTime: 5 * 60 * 1000 })
}

export function useFinanceOptions() {
  return useQuery({ queryKey: [...FINANCE_KEY, 'options'], queryFn: financeApi.options, staleTime: 5 * 60 * 1000 })
}

/** После любой денежной операции — обновить списки, бейджи, карточку. */
export function useInvalidateFinance() {
  const client = useQueryClient()
  return () => client.invalidateQueries({ queryKey: FINANCE_KEY })
}

const STAGE: Record<PaymentStage, { tone: BadgeTone; label: string }> = {
  awaiting: { tone: 'info', label: 'Ожидается оплата' },
  deadline: { tone: 'warning', label: 'Последний срок' },
  overdue: { tone: 'danger', label: 'Просрочка' },
  paid: { tone: 'success', label: 'Оплачено' },
  draft: { tone: 'muted', label: 'На согласовании' },
  void: { tone: 'muted', label: 'Аннулировано' },
}

export function StageBadge({ stage }: { stage: PaymentStage }) {
  return <Badge tone={STAGE[stage].tone}>{STAGE[stage].label}</Badge>
}

const INVOICE_TONE: Record<InvoiceStatus, BadgeTone> = {
  DRAFT: 'muted', OPEN: 'info', PARTIALLY_PAID: 'warning', PAID: 'success', OVERDUE: 'danger', VOID: 'muted',
}

export function InvoiceStatusBadge({ status, label }: { status: InvoiceStatus; label: string }) {
  return <Badge tone={INVOICE_TONE[status]}>{label}</Badge>
}

const CONTRACT_TONE: Record<ContractStatus, BadgeTone> = {
  ACTIVE: 'success', PAUSED: 'warning', INACTIVE: 'muted', COMPLETED: 'info',
}

export function ContractStatusBadge({ status, label }: { status: ContractStatus; label: string }) {
  return <Badge tone={CONTRACT_TONE[status]}>{label}</Badge>
}

/** «Месяц 2 из 6 · IT 2 из 12 · курс 14 из 72» с полоской прогресса. Все числа —
 * из backend (`progress.study_progress`): засчитанные ученику уроки, не занятия группы. */
export function MonthProgress({ month, months, used, total, courseCounted, courseTotal, billingMonth }: {
  month: number | null
  months: number | null
  used: number
  total: number
  courseCounted?: number | null
  courseTotal?: number | null
  /** Платёжный цикл уже следующего месяца (граница 12/12) — подсказка про начисление. */
  billingMonth?: number | null
}) {
  const percent = total ? Math.min(100, Math.round((used / total) * 100)) : 0
  return (
    <div className="min-w-32">
      <p className="whitespace-nowrap text-sm text-ink">
        {month ? `Месяц ${month}${months ? ` из ${months}` : ''}` : '—'}
      </p>
      <div className="mt-1 flex items-center gap-2">
        <div className="h-1.5 w-20 overflow-hidden rounded-full bg-surface-hover" aria-hidden>
          <div className="h-full rounded-full bg-brand-500" style={{ width: `${percent}%` }} />
        </div>
        <span className="whitespace-nowrap text-xs text-ink-secondary">IT {used} из {total}</span>
      </div>
      {courseTotal ? <p className="whitespace-nowrap text-xs text-ink-secondary">курс {courseCounted ?? 0} из {courseTotal}</p> : null}
      {billingMonth && month && billingMonth > month ? (
        <p className="whitespace-nowrap text-xs text-ink-secondary">выставлен месяц {billingMonth}</p>
      ) : null}
    </div>
  )
}

/** Пропсы `MonthProgress` из строки списка — одинаково во всех таблицах. */
export function rowProgress(r: QueueRow) {
  return { month: r.month_number, months: r.duration_months, used: r.lessons_used, total: r.lessons_total,
    courseCounted: r.course_lessons_counted, courseTotal: r.course_lessons_total, billingMonth: r.billing_month_number }
}

export function Loadable<T>({ query, empty, emptyTitle = 'Нет данных', emptyDescription, children }: {
  query: { isLoading: boolean; isError: boolean; refetch: () => unknown; data?: T }
  empty?: (data: T) => boolean
  emptyTitle?: string
  emptyDescription?: string
  children: (data: T) => ReactNode
}) {
  if (query.isLoading) return <LoadingState />
  if (query.isError || query.data === undefined) return <ErrorState onRetry={() => query.refetch()} />
  if (empty?.(query.data)) return <EmptyState title={emptyTitle} description={emptyDescription} />
  return <>{children(query.data)}</>
}

/** Фильтры списков живут в URL: открыли карточку и вернулись «Назад» — тот же
 * поиск, фильтры, сортировка и страница. */
export function useUrlFilters(): [QueueFilters, (next: QueueFilters) => void] {
  const [params, setParams] = useSearchParams()
  const num = (key: string) => (params.get(key) ? Number(params.get(key)) : undefined)
  const filters: QueueFilters = {
    search: params.get('search') ?? undefined,
    group: num('group'),
    program: num('program'),
    plan: num('plan'),
    ordering: params.get('ordering') ?? undefined,
    contract_status: (params.get('contract_status') as ContractStatus | null) ?? undefined,
    page: num('page') ?? 1,
  }
  const set = (next: QueueFilters) => {
    const out = new URLSearchParams()
    for (const [key, value] of Object.entries(next)) {
      if (value !== undefined && value !== null && value !== '' && !(key === 'page' && value === 1)) out.set(key, String(value))
    }
    setParams(out, { replace: true })
  }
  return [filters, set]
}

export function ListFilters({ filters, onChange, options, orderings, extra }: {
  filters: QueueFilters
  onChange: (f: QueueFilters) => void
  options?: FinanceOptions
  orderings?: { value: string; label: string }[]
  extra?: ReactNode
}) {
  const num = (v: string) => (v ? Number(v) : undefined)
  return (
    <FilterBar>
      <FilterField size="lg">
        <SearchInput value={filters.search ?? ''} placeholder="Имя, телефон или группа"
          onChange={(search) => onChange({ ...filters, search: search || undefined, page: 1 })} />
      </FilterField>
      <FilterField>
        <Select aria-label="Программа" value={filters.program ? String(filters.program) : ''} placeholder="Все программы"
          options={(options?.programs ?? []).map((p) => ({ value: String(p.id), label: p.name }))}
          onChange={(e) => onChange({ ...filters, program: num(e.target.value), page: 1 })} />
      </FilterField>
      <FilterField>
        <Select aria-label="Группа" value={filters.group ? String(filters.group) : ''} placeholder="Все группы"
          options={(options?.groups ?? []).map((g) => ({ value: String(g.id), label: g.name }))}
          onChange={(e) => onChange({ ...filters, group: num(e.target.value), page: 1 })} />
      </FilterField>
      {orderings ? (
        <FilterField>
          <Select aria-label="Сортировка" value={filters.ordering ?? ''} placeholder="Сортировка по умолчанию"
            options={orderings} onChange={(e) => onChange({ ...filters, ordering: e.target.value || undefined })} />
        </FilterField>
      ) : null}
      {extra}
    </FilterBar>
  )
}

export function Amount({ value, tone }: { value: string | null | undefined; tone?: 'danger' | 'muted' | 'brand' }) {
  return (
    <span className={cn('whitespace-nowrap tabular-nums', tone === 'danger' && 'font-semibold text-danger',
      tone === 'muted' && 'text-ink-secondary', tone === 'brand' && 'font-semibold text-brand-700')}>
      {som(value)}
    </span>
  )
}

/** Звонок / сообщение родителю — новая запись журнала, история не меняется. */
export function ContactModal({ profile, student, onClose }: { profile: number; student: string; onClose: () => void }) {
  const options = useFinanceOptions()
  const invalidate = useInvalidateFinance()
  const { run, busy } = useRunner()
  const [channel, setChannel] = useState('CALL')
  const [result, setResult] = useState('ANSWERED')
  const [comment, setComment] = useState('')
  const [promised, setPromised] = useState('')
  const [next, setNext] = useState('')

  async function submit() {
    const ok = await run(() => financeApi.addContact({
      profile, channel, result, comment, promised_payment_date: promised || null, next_contact_date: next || null,
    }), 'Контакт записан')
    if (ok) {
      invalidate()
      onClose()
    }
  }

  return (
    <Modal isOpen onClose={onClose} title={`Контакт с родителем: ${student}`}>
      <div className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Канал" htmlFor="ct-channel">
            <Select id="ct-channel" value={channel} onChange={(e) => setChannel(e.target.value)}
              options={options.data?.contact_channels ?? [{ value: 'CALL', label: 'Звонок' }]} />
          </Field>
          <Field label="Результат" htmlFor="ct-result">
            <Select id="ct-result" value={result} onChange={(e) => setResult(e.target.value)}
              options={options.data?.contact_results ?? [{ value: 'ANSWERED', label: 'Ответил' }]} />
          </Field>
          {result === 'PROMISED' ? (
            <Field label="Обещанная дата оплаты" htmlFor="ct-promised" required>
              <Input id="ct-promised" type="date" value={promised} onChange={(e) => setPromised(e.target.value)} />
            </Field>
          ) : null}
          <Field label="Следующий контакт" htmlFor="ct-next" required={result === 'FOLLOW_UP'}>
            <Input id="ct-next" type="date" value={next} onChange={(e) => setNext(e.target.value)} />
          </Field>
        </div>
        <Field label="Комментарий" htmlFor="ct-comment">
          <Textarea id="ct-comment" rows={3} value={comment} onChange={(e) => setComment(e.target.value)} />
        </Field>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>Отмена</Button>
          <Button onClick={submit} isLoading={busy}>Записать</Button>
        </div>
      </div>
    </Modal>
  )
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: 'danger' | 'warning' | 'brand' }) {
  return (
    <div className="card p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-secondary">{label}</p>
      <p className={cn('mt-1 text-xl font-semibold tabular-nums text-ink', tone === 'danger' && 'text-danger',
        tone === 'warning' && 'text-warning', tone === 'brand' && 'text-brand-700')}>{value}</p>
      {hint ? <p className="mt-1 text-xs text-ink-secondary">{hint}</p> : null}
    </div>
  )
}
