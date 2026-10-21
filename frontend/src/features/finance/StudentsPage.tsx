import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { FilePlus2 } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'

import { financeApi } from '@/api/finance'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { DataTable } from '@/components/ui/DataTable'
import { FilterField } from '@/components/ui/FilterBar'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import type { ContractStatus, QueueRow } from '@/types/finance'

import {
  Amount,
  ContractStatusBadge,
  FINANCE_KEY,
  ListFilters,
  Loadable,
  MonthProgress,
  StageBadge,
  useFinanceMe,
  useFinanceOptions,
  useUrlFilters,
} from './ui'

const PAGE_SIZE = 25

export function StudentsPage() {
  const [view, setView] = useState<'contracts' | 'unregistered'>('contracts')
  const me = useFinanceMe()
  return (
    <div>
      <PageHeader title="Все студенты"
        description="Договоры на обучение и их платёжный статус. Студенты без договора — во вкладке «Без договора»." />
      <SegmentedControl aria-label="Вид" className="mb-4" value={view} onChange={setView} options={[
        { value: 'contracts', label: 'Договоры' },
        { value: 'unregistered', label: 'Без договора' },
      ]} />
      {view === 'contracts' ? <Contracts money={me.data?.can_view_money ?? false} /> : <Unregistered canRegister={me.data?.can_register ?? false} />}
    </div>
  )
}

function Contracts({ money }: { money: boolean }) {
  const navigate = useNavigate()
  const location = useLocation()
  const options = useFinanceOptions()
  const [filters, setFilters] = useUrlFilters()
  const query = useQuery({
    queryKey: [...FINANCE_KEY, 'queue', 'all', filters],
    queryFn: () => financeApi.queue('all', { ...filters, page_size: PAGE_SIZE }),
    placeholderData: keepPreviousData,
  })
  return (
    <>
      <ListFilters filters={filters} onChange={setFilters} options={options.data}
        orderings={[{ value: 'name', label: 'По имени' }, { value: 'debt', label: 'По долгу' }, { value: 'group', label: 'По группе' }]}
        extra={
          <FilterField>
            <Select aria-label="Статус договора" value={filters.contract_status ?? ''} placeholder="Все договоры"
              options={options.data?.contract_statuses ?? []}
              onChange={(e) => setFilters({ ...filters, contract_status: (e.target.value || undefined) as ContractStatus | undefined, page: 1 })} />
          </FilterField>
        } />
      <div className="mt-4">
        <Loadable query={query} empty={(d) => d.count === 0} emptyTitle="Договоров не найдено">
          {(data) => (
            <>
              <DataTable<QueueRow>
                rows={data.results} getRowKey={(r) => r.profile}
                onRowClick={(r) => navigate(`/finance/students/${r.profile}`, { state: { from: location.pathname + location.search } })}
                columns={[
                  { key: 'student', header: 'Студент', render: (r) => (
                    <div><p className="font-medium text-ink">{r.student_name}</p>
                      <p className="text-xs text-ink-secondary">{r.group_name ?? 'Без группы'} · {r.parent_phone || 'нет телефона'}</p></div>
                  ) },
                  { key: 'program', header: 'Программа', render: (r) => (
                    <div className="text-sm"><p>{r.program ?? r.plan_name}</p><p className="text-xs text-ink-secondary">{r.payment_mode_display}</p></div>
                  ) },
                  { key: 'month', header: 'Учебный месяц', render: (r) => <MonthProgress month={r.month_number} months={r.duration_months} used={r.lessons_used} total={r.lessons_total} /> },
                  { key: 'price', header: 'Стоимость курса', render: (r) => (
                    <div><Amount value={r.final_course_price} />
                      {r.discount_amount && r.discount_amount !== '0.00' ? <p className="text-xs text-ink-secondary">скидка <Amount value={r.discount_amount} tone="muted" /></p> : null}</div>
                  ) },
                  ...(money ? [
                    { key: 'due', header: 'К оплате сейчас', render: (r: QueueRow) => <Amount value={r.due_now} tone={r.overdue_amount !== '0.00' ? 'danger' : undefined} /> },
                    { key: 'credit', header: 'Аванс', render: (r: QueueRow) => <Amount value={r.credit} tone="muted" /> },
                  ] : []),
                  { key: 'stage', header: 'Статус', render: (r) => (
                    <div className="flex flex-wrap gap-1"><StageBadge stage={r.stage} />
                      {r.contract_status !== 'ACTIVE' ? <ContractStatusBadge status={r.contract_status} label={r.contract_status_display} /> : null}</div>
                  ) },
                ]}
              />
              <div className="mt-3">
                <Pagination page={data.page} pageSize={data.page_size} totalCount={data.count}
                  onPageChange={(page) => setFilters({ ...filters, page })} />
              </div>
            </>
          )}
        </Loadable>
      </div>
    </>
  )
}

function Unregistered({ canRegister }: { canRegister: boolean }) {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const query = useQuery({
    queryKey: [...FINANCE_KEY, 'lms-students', search, page],
    queryFn: () => financeApi.lmsStudents({ search: search || undefined, registered: 'no', page }),
    placeholderData: keepPreviousData,
  })
  return (
    <>
      <div className="max-w-md"><SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1) }} placeholder="Имя или телефон" /></div>
      <div className="mt-4">
        <Loadable query={query} empty={(d) => d.count === 0} emptyTitle="Все активные студенты уже с договором">
          {(data) => (
            <>
              <DataTable rows={data.results} getRowKey={(r) => r.id} columns={[
                { key: 'name', header: 'Студент', render: (r) => <span className="font-medium">{r.name}</span> },
                { key: 'group', header: 'Группа', render: (r) => r.group_name ?? '—' },
                { key: 'phone', header: 'Телефон родителя', render: (r) => r.parent_phone || '—' },
                { key: 'act', header: '', className: 'text-right', render: (r) => canRegister ? (
                  <Button size="sm" variant="secondary" leftIcon={<FilePlus2 className="size-4" />}
                    onClick={() => navigate(`/finance/contracts/new?student=${r.id}`)}>Оформить договор</Button>
                ) : null },
              ]} />
              <div className="mt-3"><Pagination page={page} pageSize={50} totalCount={data.count} onPageChange={setPage} /></div>
            </>
          )}
        </Loadable>
      </div>
    </>
  )
}
