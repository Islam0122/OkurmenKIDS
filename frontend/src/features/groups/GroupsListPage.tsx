import { useState } from 'react'
import { CalendarClock, Users } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'

import { GroupCard } from '@/components/academy/GroupCard'
import { PageHeader } from '@/components/layout/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { Button } from '@/components/ui/Button'
import { useAuth } from '@/hooks/useAuth'
import { useGroups } from '@/hooks/useGroups'
import { seesWholeAcademy } from '@/lib/roles'
import type { GroupStatus } from '@/types/academy'
import { SubjectStartDatesModal } from './SubjectStartDatesModal'

const STATUS_OPTIONS: { value: GroupStatus; label: string }[] = [
  { value: 'active', label: 'Активна' },
  { value: 'paused', label: 'Приостановлена' },
  { value: 'completed', label: 'Завершена' },
  { value: 'cancelled', label: 'Отменена' },
]

export function GroupsListPage() {
  const [search, setSearch] = useState('')
  // The status filter lives in the URL (?status=active) so a menu link
  // («Активные группы», «Архив») can open the list already filtered.
  const [params, setParams] = useSearchParams()
  const status = STATUS_OPTIONS.some((o) => o.value === params.get('status')) ? (params.get('status') as string) : ''
  const setStatus = (value: string) => setParams(value ? { status: value } : {}, { replace: true })
  const [page, setPage] = useState(1)
  const { user } = useAuth()
  // Admin / Team Lead (backend: CanManageSubjectStartDates); a trainer only reads the dates on the group page.
  const managesStarts = seesWholeAcademy(user?.role)
  const [startsOpen, setStartsOpen] = useState(false)

  const { data, isPending, isError, refetch } = useGroups({
    search: search || undefined,
    status: (status || undefined) as GroupStatus | undefined,
    page,
  })

  return (
    <div>
      <PageHeader
        title="Мои группы"
        description="Группы, с которыми вы работаете."
        actions={
          managesStarts ? (
            <Button variant="secondary" size="sm" leftIcon={<CalendarClock className="size-4" aria-hidden />} onClick={() => setStartsOpen(true)}>
              Даты старта предметов
            </Button>
          ) : undefined
        }
      />
      {managesStarts ? <SubjectStartDatesModal isOpen={startsOpen} onClose={() => setStartsOpen(false)} /> : null}

      <FilterBar>
        <FilterField size="lg">
          <SearchInput value={search} onChange={(value) => { setSearch(value); setPage(1) }} placeholder="Поиск по названию…" />
        </FilterField>
        <FilterField>
          <Select
            aria-label="Статус"
            placeholder="Все статусы"
            value={status}
            onChange={(event) => { setStatus(event.target.value); setPage(1) }}
            options={STATUS_OPTIONS}
          />
        </FilterField>
      </FilterBar>

      {isPending ? <LoadingState label="Загружаем группы…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}

      {data && data.results.length === 0 ? (
        <EmptyState icon={Users} title="Групп не найдено" description="Попробуйте изменить фильтры или поиск." />
      ) : null}

      {data && data.results.length > 0 ? (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {data.results.map((group) => (
              <GroupCard key={group.id} group={group} />
            ))}
          </div>
          <div className="mt-6">
            <Pagination page={page} pageSize={20} totalCount={data.count} onPageChange={setPage} />
          </div>
        </>
      ) : null}
    </div>
  )
}
