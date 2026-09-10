import { useMemo, useState } from 'react'
import { useQueries } from '@tanstack/react-query'
import { ClipboardList } from 'lucide-react'

import { homeworkApi } from '@/api/homework'
import { HomeworkCard } from '@/components/academy/HomeworkCard'
import { PageHeader } from '@/components/layout/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { useGroups } from '@/hooks/useGroups'
import { useHomeworkList } from '@/hooks/useHomework'

export function HomeworkListPage() {
  const [search, setSearch] = useState('')
  const [groupId, setGroupId] = useState('')
  const [page, setPage] = useState(1)

  const { data: groupsData } = useGroups({})

  const { data, isPending, isError, refetch } = useHomeworkList({
    search: search || undefined,
    group: groupId ? Number(groupId) : undefined,
    ordering: '-created_at',
    page,
  })

  const homeworkIds = useMemo(() => data?.results.map((item) => item.id) ?? [], [data])

  // Bounded to the current page (backend PAGE_SIZE = 20) — same reasoning as the
  // dashboard's fetchAllPages aggregations: real per-student rows fetched once,
  // never a fabricated submitted/checked/pending breakdown.
  const rosterQueries = useQueries({
    queries: homeworkIds.map((id) => ({
      queryKey: ['homework', 'detail', id, 'results'],
      queryFn: () => homeworkApi.getResultsRoster(id),
    })),
  })

  const breakdownByHomeworkId = useMemo(() => {
    const map = new Map<number, { submitted: number; checked: number; pending: number; total: number }>()
    homeworkIds.forEach((id, index) => {
      const roster = rosterQueries[index]?.data
      if (!roster) return
      map.set(id, {
        submitted: roster.filter((row) => row.status === 'submitted' || row.status === 'late').length,
        checked: roster.filter((row) => row.status === 'checked').length,
        pending: roster.filter((row) => row.status === 'not_submitted').length,
        total: roster.length,
      })
    })
    return map
  }, [homeworkIds, rosterQueries])

  function updateAndResetPage<T>(setter: (value: T) => void) {
    return (value: T) => {
      setter(value)
      setPage(1)
    }
  }

  return (
    <div>
      <PageHeader title="Домашние задания" description="Все заданные вами домашние работы." />

      <div className="mb-5 flex flex-wrap gap-3">
        <div className="w-full max-w-xs">
          <SearchInput value={search} onChange={updateAndResetPage(setSearch)} placeholder="Поиск по названию…" />
        </div>
        <div className="w-56">
          <Select
            aria-label="Группа"
            placeholder="Все группы"
            value={groupId}
            onChange={(event) => updateAndResetPage(setGroupId)(event.target.value)}
            options={(groupsData?.results ?? []).map((group) => ({ value: String(group.id), label: group.name }))}
          />
        </div>
      </div>

      {isPending ? <LoadingState label="Загружаем домашние задания…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}

      {data && data.results.length === 0 ? (
        <EmptyState icon={ClipboardList} title="Домашних заданий нет" description="Попробуйте изменить фильтры." />
      ) : null}

      {data && data.results.length > 0 ? (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {data.results.map((homework) => {
              const breakdown = breakdownByHomeworkId.get(homework.id)
              return (
                <HomeworkCard
                  key={homework.id}
                  homework={homework}
                  submitted={breakdown?.submitted}
                  checked={breakdown?.checked}
                  pending={breakdown?.pending}
                  totalStudents={breakdown?.total}
                />
              )
            })}
          </div>
          <div className="mt-5">
            <Pagination page={page} pageSize={20} totalCount={data.count} onPageChange={setPage} />
          </div>
        </>
      ) : null}
    </div>
  )
}
