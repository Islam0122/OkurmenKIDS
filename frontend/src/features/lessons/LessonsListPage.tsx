import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BookOpen } from 'lucide-react'

import { subjectsApi } from '@/api/subjects'
import { LessonCard } from '@/components/academy/LessonCard'
import { PageHeader } from '@/components/layout/PageHeader'
import { DatePicker } from '@/components/ui/DatePicker'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Pagination } from '@/components/ui/Pagination'
import { Select } from '@/components/ui/Select'
import { useGroups } from '@/hooks/useGroups'
import { useLessons } from '@/hooks/useLessons'
import type { LessonStatus } from '@/types/academy'

const STATUS_OPTIONS: { value: LessonStatus; label: string }[] = [
  { value: 'planned', label: 'Запланировано' },
  { value: 'completed', label: 'Проведено' },
  { value: 'cancelled', label: 'Отменено' },
]

export function LessonsListPage() {
  const [date, setDate] = useState('')
  const [groupId, setGroupId] = useState('')
  const [subjectId, setSubjectId] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)

  const { data: groupsData } = useGroups({})
  const { data: subjectsData } = useQuery({ queryKey: ['subjects', 'list'], queryFn: () => subjectsApi.list({ is_active: true }) })

  const { data, isPending, isError, refetch } = useLessons({
    date: date || undefined,
    group: groupId ? Number(groupId) : undefined,
    subject: subjectId ? Number(subjectId) : undefined,
    status: (status || undefined) as LessonStatus | undefined,
    ordering: '-date',
    page,
  })

  function resetPage<T>(setter: (value: T) => void) {
    return (value: T) => {
      setter(value)
      setPage(1)
    }
  }

  return (
    <div>
      <PageHeader title="Занятия" description="Все ваши занятия — прошедшие и предстоящие." />

      <div className="mb-5 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <DatePicker aria-label="Дата" value={date} onChange={(event) => resetPage(setDate)(event.target.value)} />
        <Select
          aria-label="Группа"
          placeholder="Все группы"
          value={groupId}
          onChange={(event) => resetPage(setGroupId)(event.target.value)}
          options={(groupsData?.results ?? []).map((group) => ({ value: String(group.id), label: group.name }))}
        />
        <Select
          aria-label="Предмет"
          placeholder="Все предметы"
          value={subjectId}
          onChange={(event) => resetPage(setSubjectId)(event.target.value)}
          options={(subjectsData?.results ?? []).map((subject) => ({ value: String(subject.id), label: subject.name }))}
        />
        <Select
          aria-label="Статус"
          placeholder="Все статусы"
          value={status}
          onChange={(event) => resetPage(setStatus)(event.target.value)}
          options={STATUS_OPTIONS}
        />
      </div>

      {isPending ? <LoadingState label="Загружаем занятия…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}

      {data && data.results.length === 0 ? (
        <EmptyState icon={BookOpen} title="Занятия не найдены" description="Попробуйте изменить фильтры." />
      ) : null}

      {data && data.results.length > 0 ? (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {data.results.map((lesson) => (
              <LessonCard key={lesson.id} lesson={lesson} />
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
