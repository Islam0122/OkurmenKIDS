import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { History, Phone, Plus, UserRound } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'

import { financeApi } from '@/api/finance'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { DataTable } from '@/components/ui/DataTable'
import type { DataTableColumn } from '@/components/ui/DataTable'
import { Pagination } from '@/components/ui/Pagination'
import type { QueueKind, QueueRow } from '@/types/finance'

import {
  Amount,
  ContactModal,
  FINANCE_KEY,
  ListFilters,
  Loadable,
  MonthProgress,
  rowProgress,
  StageBadge,
  formatDateTime,
  useFinanceMe,
  useFinanceOptions,
  useUrlFilters,
} from './ui'

const PAGE_SIZE = 25

const META: Record<Exclude<QueueKind, 'all'>, { title: string; description: string; empty: string }> = {
  to_pay: {
    title: 'К оплате',
    description: 'Наступил платёжный этап: учебный месяц начался, начисление выставлено. Срок — не позднее указанного урока IT месяца.',
    empty: 'Сейчас никто не ждёт оплаты',
  },
  soon: {
    title: 'Скоро оплата',
    description: 'До конца учебного месяца осталось 3 урока IT или меньше, а следующий месяц ещё не оплачен.',
    empty: 'В ближайшие уроки никому не предстоит оплата',
  },
  overdue: {
    title: 'Просроченные',
    description: 'Срок оплаты прошёл, а обязательство не погашено. Бронь сама по себе долгом не считается.',
    empty: 'Просроченных оплат нет',
  },
}

const ORDERINGS = {
  to_pay: [{ value: 'debt', label: 'По сумме долга' }, { value: 'name', label: 'По имени' }, { value: 'group', label: 'По группе' }],
  soon: [{ value: 'lessons', label: 'Ближе к концу месяца' }, { value: 'name', label: 'По имени' }, { value: 'group', label: 'По группе' }],
  overdue: [{ value: 'overdue', label: 'Дольше всех просрочено' }, { value: 'debt', label: 'По сумме долга' },
    { value: 'name', label: 'По имени' }],
}

function StudentCell({ row }: { row: QueueRow }) {
  return (
    <div className="min-w-40">
      <p className="font-medium text-ink">{row.student_name}</p>
      <p className="text-xs text-ink-secondary">{row.group_name ?? 'Без группы'}{row.program ? ` · ${row.program}` : ''}</p>
    </div>
  )
}

function deadlineText(row: QueueRow): string {
  const inv = row.focus_invoice
  if (!inv) return '—'
  if (inv.due_lesson) return inv.kind === 'COURSE'
    ? `Весь курс: до ${inv.due_lesson}-го урока IT первого месяца`
    : `${inv.due_lesson}-й урок IT месяца ${inv.month_number}`
  return inv.due_date ?? '—'
}

export function QueuePage({ queue }: { queue: Exclude<QueueKind, 'all'> }) {
  const meta = META[queue]
  const navigate = useNavigate()
  const location = useLocation()
  const me = useFinanceMe()
  const options = useFinanceOptions()
  const [filters, setFilters] = useUrlFilters()
  const [contact, setContact] = useState<QueueRow | null>(null)
  const query = useQuery({
    queryKey: [...FINANCE_KEY, 'queue', queue, filters],
    queryFn: () => financeApi.queue(queue, { ...filters, page_size: PAGE_SIZE }),
    placeholderData: keepPreviousData,
  })
  const canPay = me.data?.can_record_payments ?? false
  const open = (row: QueueRow) => navigate(`/finance/students/${row.profile}`, { state: { from: location.pathname + location.search } })

  const actions: DataTableColumn<QueueRow> = {
    key: 'actions', header: '', className: 'text-right',
    render: (row) => (
      <div className="flex justify-end gap-1" onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()} role="presentation">
        {canPay ? (
          <Button size="sm" leftIcon={<Plus className="size-4" />}
            onClick={() => navigate(`/finance/payments/new?profile=${row.profile}${row.focus_invoice ? `&invoice=${row.focus_invoice.id}` : ''}`)}>
            Платёж
          </Button>
        ) : null}
        {canPay ? (
          <Button size="sm" variant="ghost" aria-label="Контакт с родителем" title="Зафиксировать контакт" onClick={() => setContact(row)}>
            <Phone className="size-4" />
          </Button>
        ) : null}
        <Button size="sm" variant="ghost" aria-label="История платежей" title="История платежей"
          onClick={() => navigate(`/finance/students/${row.profile}#payments`)}>
          <History className="size-4" />
        </Button>
        <Button size="sm" variant="ghost" aria-label="Карточка студента" title="Карточка студента" onClick={() => open(row)}>
          <UserRound className="size-4" />
        </Button>
      </div>
    ),
  }

  const columns: Record<typeof queue, DataTableColumn<QueueRow>[]> = {
    to_pay: [
      { key: 'student', header: 'Студент', render: (r) => <StudentCell row={r} /> },
      { key: 'month', header: 'Учебный месяц', render: (r) => <MonthProgress {...rowProgress(r)} /> },
      { key: 'cost', header: 'Начислено', render: (r) => <Amount value={r.focus_invoice?.amount} /> },
      { key: 'paid', header: 'Получено', render: (r) => <Amount value={r.focus_invoice?.paid} tone="muted" /> },
      { key: 'balance', header: 'Остаток', render: (r) => <Amount value={r.focus_invoice?.balance} tone="brand" /> },
      { key: 'due', header: 'Срок оплаты', render: (r) => (
        <div className="space-y-1"><p className="text-sm">{deadlineText(r)}</p><StageBadge stage={r.stage} /></div>
      ) },
      actions,
    ],
    soon: [
      { key: 'student', header: 'Студент', render: (r) => <StudentCell row={r} /> },
      { key: 'month', header: 'Учебный месяц', render: (r) => <MonthProgress {...rowProgress(r)} /> },
      { key: 'left', header: 'Осталось уроков', render: (r) => <span className="font-semibold">{r.lessons_total - r.lessons_used}</span> },
      { key: 'next', header: 'Следующий месяц', render: (r) => <Amount value={r.next_month?.cost} /> },
      { key: 'covered', header: 'Внесено авансом', render: (r) => <Amount value={r.next_month?.covered} tone="muted" /> },
      { key: 'to_pay', header: 'К оплате', render: (r) => <Amount value={r.next_month?.to_pay} tone="brand" /> },
      actions,
    ],
    overdue: [
      { key: 'student', header: 'Студент', render: (r) => <StudentCell row={r} /> },
      { key: 'debt', header: 'Долг', render: (r) => <Amount value={r.overdue_amount} tone="danger" /> },
      { key: 'late', header: 'Просрочка', render: (r) => (
        <div className="text-sm">
          {r.overdue_lessons ? <p className="whitespace-nowrap">{r.overdue_lessons} ур. после срока</p> : null}
          <p className="text-ink-secondary">{r.overdue_days} дн.</p>
        </div>
      ) },
      { key: 'month', header: 'Учебный месяц', render: (r) => <MonthProgress {...rowProgress(r)} /> },
      { key: 'parent', header: 'Родитель', render: (r) => (
        <div className="text-sm"><p>{r.parent_name || '—'}</p>
          {r.parent_phone ? <a className="whitespace-nowrap text-brand-700 hover:underline" href={`tel:${r.parent_phone}`} onClick={(e) => e.stopPropagation()}>{r.parent_phone}</a> : null}
        </div>
      ) },
      { key: 'contact', header: 'Последний контакт', render: (r) => (
        <div className="text-sm"><p>{r.last_contact_at ? formatDateTime(r.last_contact_at) : 'Не звонили'}</p>
          <p className="text-xs text-ink-secondary">{r.last_contact_result ?? ''}</p></div>
      ) },
      actions,
    ],
  }

  return (
    <div>
      <PageHeader title={meta.title} description={meta.description}
        badge={query.data ? <span className="rounded-full bg-surface-hover px-2.5 py-1 text-sm text-ink-secondary">{query.data.count}</span> : undefined} />
      <ListFilters filters={filters} onChange={setFilters} options={options.data} orderings={ORDERINGS[queue]} />
      <div className="mt-4">
        <Loadable query={query} empty={(d) => d.count === 0} emptyTitle={meta.empty}
          emptyDescription={filters.search || filters.group || filters.program ? 'Попробуйте изменить фильтры.' : undefined}>
          {(data) => (
            <>
              <DataTable columns={columns[queue]} rows={data.results} getRowKey={(r) => r.profile} onRowClick={open} />
              <div className="mt-3">
                <Pagination page={data.page} pageSize={data.page_size} totalCount={data.count}
                  onPageChange={(page) => setFilters({ ...filters, page })} />
              </div>
            </>
          )}
        </Loadable>
      </div>
      {contact ? <ContactModal profile={contact.profile} student={contact.student_name} onClose={() => setContact(null)} /> : null}
    </div>
  )
}

export function ToPayPage() {
  return <QueuePage queue="to_pay" />
}

export function SoonPage() {
  return <QueuePage queue="soon" />
}

export function OverduePage() {
  return <QueuePage queue="overdue" />
}
