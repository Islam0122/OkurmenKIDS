import { useState } from 'react'
import { GraduationCap } from 'lucide-react'

import { StudentCard } from '@/components/academy/StudentCard'
import { PageHeader } from '@/components/layout/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { useGroups } from '@/hooks/useGroups'
import { useStudents } from '@/hooks/useStudents'

export function StudentsListPage() {
  const [search, setSearch] = useState('')
  const [groupId, setGroupId] = useState('')
  const [page, setPage] = useState(1)

  const { data: groupsData } = useGroups({})
  const { data, isPending, isError, refetch } = useStudents({
    search: search || undefined,
    group: groupId ? Number(groupId) : undefined,
    page,
  })

  return (
    <div>
      <PageHeader title="Студенты" description="Студенты ваших групп." />

      <FilterBar>
        <FilterField size="lg">
          <SearchInput
            value={search}
            onChange={(value) => {
              setSearch(value)
              setPage(1)
            }}
            placeholder="Имя, фамилия или телефон…"
          />
        </FilterField>
        <FilterField>
          <Select
            aria-label="Группа"
            placeholder="Все группы"
            value={groupId}
            onChange={(event) => {
              setGroupId(event.target.value)
              setPage(1)
            }}
            options={(groupsData?.results ?? []).map((group) => ({ value: String(group.id), label: group.name }))}
          />
        </FilterField>
      </FilterBar>

      {isPending ? <LoadingState label="Загружаем студентов…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}

      {data && data.results.length === 0 ? (
        <EmptyState icon={GraduationCap} title="Студенты не найдены" description="Попробуйте изменить фильтры или поиск." />
      ) : null}

      {data && data.results.length > 0 ? (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {data.results.map((student) => (
              <StudentCard key={student.id} student={student} />
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
