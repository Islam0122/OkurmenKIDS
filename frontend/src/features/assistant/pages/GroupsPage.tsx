import { useState } from 'react'
import { CalendarDays, Plus, UserRound, Users } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'

import type { GroupListParams } from '@/api/assistant'
import { PageHeader } from '@/components/layout/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { LoadingState } from '@/components/ui/LoadingState'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { useAssistantGroups, useAssistantOptions } from '@/hooks/useAssistant'
import type { GroupCardData } from '@/types/assistant'
import { pluralize } from '@/utils/format'

import { ButtonLink, GroupStatusBadge } from '../ui'

type StatusTab = NonNullable<GroupListParams['status']>
const TABS: { value: StatusTab; label: string }[] = [
  { value: 'all', label: 'Все' },
  { value: 'active', label: 'Активные' },
  { value: 'archived', label: 'Архив' },
]

function GroupTile({ group }: { group: GroupCardData }) {
  return (
    <div className="card card-body flex min-w-0 flex-col">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="truncate text-lg font-semibold text-ink">{group.name}</h3>
          <p className="truncate text-sm text-ink-secondary">{group.course.name}</p>
        </div>
        <GroupStatusBadge status={group.status} label={group.status_display} />
      </div>
      <ul className="mt-4 flex-1 space-y-2 text-sm text-ink">
        <li className="flex items-center gap-2">
          <Users className="size-4 shrink-0 text-ink-muted" aria-hidden />
          {group.students_count}{group.max_students ? ` / ${group.max_students}` : ''} {pluralize(group.students_count, 'студент', 'студента', 'студентов')}
        </li>
        <li className="flex min-w-0 items-center gap-2">
          <UserRound className="size-4 shrink-0 text-ink-muted" aria-hidden />
          <span className="truncate">Тренер: {group.teachers.length ? group.teachers.join(', ') : <span className="text-warning">не назначен</span>}</span>
        </li>
        <li className="flex min-w-0 items-start gap-2">
          <CalendarDays className="mt-0.5 size-4 shrink-0 text-ink-muted" aria-hidden />
          <span className="min-w-0">{group.schedule || <span className="text-warning">нет расписания</span>}</span>
        </li>
      </ul>
      <Link to={`/assistant/groups/${group.id}`} className="mt-4 inline-flex h-9 items-center justify-center rounded-lg border border-brand-200 text-sm font-medium text-brand-700 hover:bg-brand-50">
        Открыть группу
      </Link>
    </div>
  )
}

export function AssistantGroupsPage() {
  const [params, setParams] = useSearchParams()
  const status = (TABS.some((t) => t.value === params.get('status')) ? params.get('status') : 'active') as StatusTab
  const [search, setSearch] = useState('')
  const [course, setCourse] = useState('')
  const [teacher, setTeacher] = useState('')
  const [page, setPage] = useState(1)
  const { data: options } = useAssistantOptions()
  const { data, isPending, isError, refetch } = useAssistantGroups({
    status,
    search: search || undefined,
    course: course ? Number(course) : undefined,
    teacher: teacher ? Number(teacher) : undefined,
    page,
  })
  const filtered = Boolean(search || course || teacher)

  return (
    <div>
      <PageHeader
        title="Группы"
        description="Все группы академии: состав, тренер, расписание."
        actions={<ButtonLink to="/assistant/groups/create" icon={<Plus className="size-4" aria-hidden />}>Создать группу</ButtonLink>}
      />
      <FilterBar>
        <FilterField size="lg">
          <SearchInput value={search} onChange={(value) => { setSearch(value); setPage(1) }} placeholder="Поиск групп…" />
        </FilterField>
        <FilterField>
          <Select aria-label="Курс" value={course} placeholder="Все курсы" onChange={(e) => { setCourse(e.target.value); setPage(1) }}
            options={(options?.courses ?? []).map((c) => ({ value: String(c.id), label: c.name }))} />
        </FilterField>
        <FilterField>
          <Select aria-label="Тренер" value={teacher} placeholder="Все тренеры" onChange={(e) => { setTeacher(e.target.value); setPage(1) }}
            options={(options?.teachers ?? []).map((t) => ({ value: String(t.id), label: t.name }))} />
        </FilterField>
        <SegmentedControl aria-label="Статус групп" options={TABS} value={status}
          onChange={(value) => { setParams(value === 'active' ? {} : { status: value }, { replace: true }); setPage(1) }} />
      </FilterBar>

      {isPending ? <LoadingState label="Загружаем группы…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}
      {data && data.results.length === 0 ? (
        filtered ? (
          <EmptyState icon={Users} title="Групп не найдено" description="Измените поиск или фильтры." />
        ) : (
          <EmptyState
            icon={Users}
            title={status === 'archived' ? 'В архиве пусто' : 'Групп пока нет'}
            description={status === 'archived' ? undefined : 'Создайте первую группу.'}
            action={status === 'archived' ? undefined : <ButtonLink to="/assistant/groups/create" icon={<Plus className="size-4" aria-hidden />}>Создать группу</ButtonLink>}
          />
        )
      ) : null}
      {data && data.results.length > 0 ? (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {data.results.map((group) => <GroupTile key={group.id} group={group} />)}
          </div>
          <div className="mt-6">
            <Pagination page={page} pageSize={20} totalCount={data.count} onPageChange={setPage} />
          </div>
        </>
      ) : null}
    </div>
  )
}
