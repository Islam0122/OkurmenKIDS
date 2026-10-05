import { useState } from 'react'
import { ArrowRightLeft, GraduationCap, Plus, UserCheck, UsersRound, UserX, X } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'

import type { StudentListParams } from '@/api/assistant'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { LoadingState } from '@/components/ui/LoadingState'
import { Menu } from '@/components/ui/Menu'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { useAssistantOptions, useAssistantStudents } from '@/hooks/useAssistant'
import type { BulkAction, StudentRow } from '@/types/assistant'

import { useAssistantActions } from '../actions/AssistantActions'
import { ButtonLink, StudentStatusBadge } from '../ui'

type StatusTab = NonNullable<StudentListParams['status']>
const TABS: { value: StatusTab; label: string }[] = [
  { value: 'all', label: 'Все' },
  { value: 'active', label: 'Активные' },
  { value: 'inactive', label: 'Неактивные' },
  { value: 'paused', label: 'На паузе' },
  { value: 'archived', label: 'Архив' },
]

const BULK: { action: BulkAction; label: string; icon: typeof UserX; tone?: 'danger' }[] = [
  { action: 'transfer', label: 'Перевести', icon: ArrowRightLeft },
  { action: 'add_to_group', label: 'В группу', icon: UsersRound },
  { action: 'activate', label: 'Активировать', icon: UserCheck },
  { action: 'deactivate', label: 'Деактивировать', icon: UserX, tone: 'danger' },
]

function RowActions({ student }: { student: StudentRow }) {
  const { open } = useAssistantActions()
  const movable = student.status === 'active' || student.status === 'paused'
  return (
    <div className="flex items-center justify-end gap-1">
      <Link to={`/assistant/students/${student.id}`} className="hidden h-8 items-center rounded-lg px-2.5 text-sm font-medium text-brand-700 hover:bg-brand-50 sm:inline-flex">
        Открыть
      </Link>
      {movable ? (
        <Button size="sm" variant="ghost" onClick={() => open({ type: 'transfer', student })} aria-label={`Перевести ${student.full_name}`}>
          <ArrowRightLeft className="size-4" aria-hidden /><span className="hidden xl:inline">Перевести</span>
        </Button>
      ) : null}
      <Menu
        label={`Действия: ${student.full_name}`}
        items={[
          student.status === 'active'
            ? { key: 'deactivate', label: 'Деактивировать', tone: 'danger' as const, icon: <UserX className="size-4" aria-hidden />, onClick: () => open({ type: 'deactivate', student }) }
            : { key: 'activate', label: 'Активировать', icon: <UserCheck className="size-4" aria-hidden />, onClick: () => open({ type: 'activate', student }), disabled: student.status === 'completed' },
        ]}
      />
    </div>
  )
}

export function AssistantStudentsPage() {
  const [params, setParams] = useSearchParams()
  const status = (TABS.some((t) => t.value === params.get('status')) ? params.get('status') : 'all') as StatusTab
  const noGroup = params.get('no_group') === '1'
  const [search, setSearch] = useState('')
  const [group, setGroup] = useState(params.get('group') ?? '')
  const [course, setCourse] = useState('')
  const [teacher, setTeacher] = useState('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<Map<number, StudentRow>>(new Map())
  const { open } = useAssistantActions()
  const { data: options } = useAssistantOptions()
  const { data, isPending, isError, refetch } = useAssistantStudents({
    status,
    search: search || undefined,
    group: group ? Number(group) : undefined,
    course: course ? Number(course) : undefined,
    teacher: teacher ? Number(teacher) : undefined,
    no_group: noGroup,
    page,
  })
  const rows = data?.results ?? []
  const allOnPageSelected = rows.length > 0 && rows.every((row) => selected.has(row.id))
  const filtered = Boolean(search || group || course || teacher || noGroup || status !== 'all')

  const toggle = (student: StudentRow) =>
    setSelected((current) => {
      const next = new Map(current)
      if (next.has(student.id)) next.delete(student.id)
      else next.set(student.id, student)
      return next
    })
  const togglePage = () =>
    setSelected((current) => {
      const next = new Map(current)
      if (allOnPageSelected) rows.forEach((row) => next.delete(row.id))
      else rows.forEach((row) => next.set(row.id, row))
      return next
    })
  const setStatus = (value: StatusTab) => {
    const next = new URLSearchParams(params)
    if (value === 'all') next.delete('status')
    else next.set('status', value)
    setParams(next, { replace: true })
    setPage(1)
  }

  return (
    <div>
      <PageHeader
        title="Студенты"
        description="Поиск, статусы, переводы и групповые действия."
        actions={<ButtonLink to="/assistant/students/create" icon={<Plus className="size-4" aria-hidden />}>Добавить студента</ButtonLink>}
      />
      <div className="mb-4">
        <SegmentedControl aria-label="Статус студентов" options={TABS} value={status} onChange={setStatus} />
      </div>
      <FilterBar>
        <FilterField size="lg">
          <SearchInput value={search} onChange={(value) => { setSearch(value); setPage(1) }} placeholder="Имя, фамилия или телефон…" />
        </FilterField>
        <FilterField>
          <Select aria-label="Группа" value={group} placeholder="Все группы" onChange={(e) => { setGroup(e.target.value); setPage(1) }}
            options={(options?.groups ?? []).map((g) => ({ value: String(g.id), label: g.name }))} />
        </FilterField>
        <FilterField>
          <Select aria-label="Программа" value={course} placeholder="Все программы" onChange={(e) => { setCourse(e.target.value); setPage(1) }}
            options={(options?.courses ?? []).map((c) => ({ value: String(c.id), label: c.name }))} />
        </FilterField>
        <FilterField>
          <Select aria-label="Тренер" value={teacher} placeholder="Все тренеры" onChange={(e) => { setTeacher(e.target.value); setPage(1) }}
            options={(options?.teachers ?? []).map((t) => ({ value: String(t.id), label: t.name }))} />
        </FilterField>
        {noGroup ? (
          <button type="button" onClick={() => { const next = new URLSearchParams(params); next.delete('no_group'); setParams(next, { replace: true }) }}
            className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-warning/30 bg-warning-soft px-3 text-sm font-medium text-warning">
            Без группы <X className="size-4" aria-hidden />
          </button>
        ) : null}
      </FilterBar>

      {selected.size > 0 ? (
        <div className="sticky top-[calc(var(--spacing-header)+0.5rem)] z-20 mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-brand-200 bg-brand-50 px-3 py-2 shadow-sm">
          <span className="mr-auto text-sm font-medium text-brand-700">Выбрано: {selected.size}</span>
          {BULK.map((item) => (
            <Button key={item.action} size="sm" variant={item.tone === 'danger' ? 'danger' : 'secondary'}
              leftIcon={<item.icon className="size-4" aria-hidden />}
              onClick={() => open({ type: 'bulk', action: item.action, students: [...selected.values()], onDone: () => setSelected(new Map()) })}>
              {item.label}
            </Button>
          ))}
          <Button size="sm" variant="ghost" onClick={() => setSelected(new Map())} aria-label="Снять выделение"><X className="size-4" aria-hidden /></Button>
        </div>
      ) : null}

      {isPending ? <LoadingState label="Загружаем студентов…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}
      {data && rows.length === 0 ? (
        <EmptyState icon={GraduationCap} title={filtered ? 'Студенты не найдены' : 'Студентов пока нет'}
          description={filtered ? 'Измените поиск или фильтры.' : undefined}
          action={<ButtonLink to="/assistant/students/create" icon={<Plus className="size-4" aria-hidden />}>Добавить студента</ButtonLink>} />
      ) : null}
      {data && rows.length > 0 ? (
        <>
          {/* Desktop / tablet: a table. */}
          <div className="card hidden overflow-x-auto md:block">
            <table className="data-table">
              <thead>
                <tr>
                  <th className="w-10"><input type="checkbox" aria-label="Выбрать всех на странице" className="size-4 accent-brand-500" checked={allOnPageSelected} onChange={togglePage} /></th>
                  <th>Имя</th><th>Группа</th><th>Программа</th><th>Статус</th><th>Посещаемость</th><th className="text-right">Действия</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((student) => (
                  <tr key={student.id} className={selected.has(student.id) ? 'bg-brand-50/50' : undefined}>
                    <td><input type="checkbox" aria-label={`Выбрать ${student.full_name}`} className="size-4 accent-brand-500" checked={selected.has(student.id)} onChange={() => toggle(student)} /></td>
                    <td className="max-w-56"><Link to={`/assistant/students/${student.id}`} className="block truncate font-medium text-ink hover:text-brand-700">{student.full_name}</Link></td>
                    <td>{student.group ? <Link to={`/assistant/groups/${student.group.id}`} className="hover:text-brand-700">{student.group.name}</Link> : <span className="text-warning">Без группы</span>}</td>
                    <td className="text-ink-secondary">{student.course?.name ?? '—'}</td>
                    <td><StudentStatusBadge status={student.status} label={student.status_display} /></td>
                    <td className="tabular-nums">{student.attendance_percent !== null ? `${student.attendance_percent}%` : '—'}</td>
                    <td><RowActions student={student} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {/* Phone: cards. */}
          <ul className="space-y-3 md:hidden">
            {rows.map((student) => (
              <li key={student.id} className="card card-body">
                <div className="flex items-start gap-3">
                  <input type="checkbox" aria-label={`Выбрать ${student.full_name}`} className="mt-1 size-4 accent-brand-500" checked={selected.has(student.id)} onChange={() => toggle(student)} />
                  <Link to={`/assistant/students/${student.id}`} className="min-w-0 flex-1">
                    <p className="truncate font-medium text-ink">{student.full_name}</p>
                    <p className="truncate text-sm text-ink-secondary">{student.group?.name ?? 'Без группы'}{student.course ? ` · ${student.course.name}` : ''}</p>
                  </Link>
                  <StudentStatusBadge status={student.status} label={student.status_display} />
                </div>
                <div className="mt-3 flex items-center justify-between gap-2">
                  <span className="text-sm text-ink-secondary">Посещаемость: {student.attendance_percent !== null ? `${student.attendance_percent}%` : '—'}</span>
                  <RowActions student={student} />
                </div>
              </li>
            ))}
          </ul>
          <div className="mt-6">
            <Pagination page={page} pageSize={20} totalCount={data.count} onPageChange={setPage} />
          </div>
        </>
      ) : null}
    </div>
  )
}
