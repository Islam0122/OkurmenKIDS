import { useState } from 'react'
import { Plus, Users } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'

import type { GroupListParams } from '@/api/assistant'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { LoadingState } from '@/components/ui/LoadingState'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { useAssistantGroups, useAssistantOptions } from '@/hooks/useAssistant'

import { useAssistantActions } from '../actions/AssistantActions'
import { GroupStatusBadge } from '../ui'

type StatusTab = NonNullable<GroupListParams['status']>
const TABS: { value: StatusTab; label: string }[] = [
  { value: 'active', label: 'Активные' },
  { value: 'archived', label: 'Архив' },
  { value: 'all', label: 'Все' },
]

/** Every group as one compact row: name, program, students, trainer, timetable. */
export function AssistantGroupsPage() {
  const [params, setParams] = useSearchParams()
  const status = (TABS.some((t) => t.value === params.get('status')) ? params.get('status') : 'active') as StatusTab
  const [search, setSearch] = useState('')
  const [course, setCourse] = useState('')
  const [teacher, setTeacher] = useState(params.get('teacher') ?? '')
  const [day, setDay] = useState('')
  const [page, setPage] = useState(1)
  const { open } = useAssistantActions()
  const { data: options } = useAssistantOptions()
  const { data, isPending, isError, refetch } = useAssistantGroups({
    status,
    search: search || undefined,
    course: course ? Number(course) : undefined,
    teacher: teacher ? Number(teacher) : undefined,
    day: day || undefined,
    page,
  })
  const filtered = Boolean(search || course || teacher || day)
  const reset = (fn: () => void) => { fn(); setPage(1) }
  const create = <Button leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => open({ type: 'create-group' })}>Группа</Button>

  return (
    <div>
      <PageHeader title="Группы" description={data ? `${data.count} ${status === 'archived' ? 'в архиве' : 'групп'}` : undefined} actions={create} />
      <FilterBar className="mb-4">
        <FilterField size="lg">
          <SearchInput value={search} onChange={(value) => reset(() => setSearch(value))} placeholder="Поиск групп…" />
        </FilterField>
        <SegmentedControl aria-label="Статус групп" options={TABS} value={status}
          onChange={(value) => reset(() => setParams(value === 'active' ? {} : { status: value }, { replace: true }))} />
        <FilterField>
          <Select aria-label="Программа" value={course} placeholder="Все программы" onChange={(e) => reset(() => setCourse(e.target.value))}
            options={(options?.courses ?? []).map((c) => ({ value: String(c.id), label: c.name }))} />
        </FilterField>
        <FilterField>
          <Select aria-label="Тренер" value={teacher} placeholder="Все тренеры" onChange={(e) => reset(() => setTeacher(e.target.value))}
            options={(options?.teachers ?? []).map((t) => ({ value: String(t.id), label: t.name }))} />
        </FilterField>
        <FilterField>
          <Select aria-label="День занятий" value={day} placeholder="Любой день" onChange={(e) => reset(() => setDay(e.target.value))}
            options={(options?.weekdays ?? []).map((d) => ({ value: d.code, label: d.label }))} />
        </FilterField>
      </FilterBar>

      {isPending ? <LoadingState label="Загружаем группы…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}
      {data && data.results.length === 0 ? (
        filtered
          ? <EmptyState icon={Users} title="Групп не найдено" description="Измените поиск или фильтры." />
          : <EmptyState icon={Users} title={status === 'archived' ? 'В архиве пусто' : 'Групп пока нет'}
              description={status === 'archived' ? undefined : 'Создайте первую группу.'} action={status === 'archived' ? undefined : create} />
      ) : null}
      {data && data.results.length > 0 ? (
        <>
          <div className="card hidden overflow-hidden md:block">
            <table className="data-table">
              <thead>
                <tr><th>Группа</th><th>Программа</th><th>Студенты</th><th>Тренер</th><th>Расписание</th><th>Статус</th></tr>
              </thead>
              <tbody>
                {data.results.map((group) => (
                  <tr key={group.id} className="hover:bg-surface-hover">
                    <td className="whitespace-nowrap"><Link to={`/assistant/groups/${group.id}`} className="font-semibold text-ink hover:text-brand-700">{group.name}</Link></td>
                    <td className="text-ink-secondary">{group.course.name}</td>
                    <td className="tabular-nums">{group.students_count}{group.max_students ? <span className="text-ink-muted"> / {group.max_students}</span> : null}</td>
                    <td className="max-w-48 truncate">{group.teachers.length ? group.teachers.join(', ') : <span className="text-warning">не назначен</span>}</td>
                    <td className="text-ink-secondary">{group.schedule || <span className="text-warning">нет расписания</span>}</td>
                    <td><GroupStatusBadge status={group.status} label={group.status_display} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="card divide-y divide-border md:hidden">
            {data.results.map((group) => (
              <li key={group.id}>
                <Link to={`/assistant/groups/${group.id}`} className="block px-4 py-3 hover:bg-surface-hover">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-ink">{group.name}</span>
                    <span className="text-sm text-ink-secondary tabular-nums">{group.students_count} студ.</span>
                  </div>
                  <p className="truncate text-sm text-ink-secondary">{group.course.name} · {group.teachers.join(', ') || 'тренер не назначен'}</p>
                  <p className="truncate text-xs text-ink-muted">{group.schedule || 'нет расписания'}</p>
                </Link>
              </li>
            ))}
          </ul>
          <div className="mt-4">
            <Pagination page={page} pageSize={20} totalCount={data.count} onPageChange={setPage} />
          </div>
        </>
      ) : null}
    </div>
  )
}
