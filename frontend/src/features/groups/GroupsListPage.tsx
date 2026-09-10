import { useState } from 'react'
import { Users } from 'lucide-react'

import { GroupCard } from '@/components/academy/GroupCard'
import { PageHeader } from '@/components/layout/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { useGroups } from '@/hooks/useGroups'
import type { GroupStatus } from '@/types/academy'

const STATUS_OPTIONS: { value: GroupStatus; label: string }[] = [
  { value: 'active', label: 'Активна' },
  { value: 'paused', label: 'Приостановлена' },
  { value: 'completed', label: 'Завершена' },
  { value: 'cancelled', label: 'Отменена' },
]

export function GroupsListPage() {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)

  const { data, isPending, isError, refetch } = useGroups({
    search: search || undefined,
    status: (status || undefined) as GroupStatus | undefined,
    page,
  })

  return (
    <div>
      <PageHeader title="Мои группы" description="Группы, с которыми вы работаете." />

      <div className="mb-5 flex flex-wrap gap-3">
        <div className="w-full max-w-xs">
          <SearchInput value={search} onChange={(value) => { setSearch(value); setPage(1) }} placeholder="Поиск по названию…" />
        </div>
        <div className="w-44">
          <Select
            aria-label="Статус"
            placeholder="Все статусы"
            value={status}
            onChange={(event) => { setStatus(event.target.value); setPage(1) }}
            options={STATUS_OPTIONS}
          />
        </div>
      </div>

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
          <div className="mt-5">
            <Pagination page={page} pageSize={20} totalCount={data.count} onPageChange={setPage} />
          </div>
        </>
      ) : null}
    </div>
  )
}
