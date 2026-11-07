import { useEffect, useMemo, useState } from 'react'
import { format, startOfMonth, startOfYear, subMonths } from 'date-fns'
import { CalendarRange, FolderKanban, GraduationCap, LayoutGrid, List, Plus, SearchX, Users } from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { ErrorState } from '@/components/ui/ErrorState'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { StatCard } from '@/components/ui/StatCard'
import { useToast } from '@/components/ui/Toast'
import { useDeleteProject, useProjectOptions, useProjects, useProjectStats } from '@/hooks/useProjects'
import { extractErrorMessage } from '@/lib/apiError'
import type { ProjectFilters, ProjectListItem, ProjectStats } from '@/types/projects'
import { cn } from '@/utils/cn'

import { ProjectCard, ProjectRow } from './ProjectCard'
import { ProjectCardSkeleton, ProjectRowSkeleton, ProjectsIllustration, useProjectsBase } from './shared'

const PAGE_SIZE = 12
const VIEW_KEY = 'okurmen.projects.view'
type ViewMode = 'grid' | 'list'

const PERIOD_OPTIONS = [
  { value: 'month', label: 'Этот месяц' },
  { value: '3m', label: 'Последние 3 месяца' },
  { value: 'year', label: 'Этот год' },
]

function periodRange(period: string): Pick<ProjectFilters, 'date_from' | 'date_to'> {
  const today = new Date()
  const iso = (d: Date) => format(d, 'yyyy-MM-dd')
  if (period === 'month') return { date_from: iso(startOfMonth(today)) }
  if (period === '3m') return { date_from: iso(startOfMonth(subMonths(today, 2))) }
  if (period === 'year') return { date_from: iso(startOfYear(today)) }
  return {}
}

/** Per-browser convenience; storage may be unavailable (private mode). */
function readView(): ViewMode {
  try {
    return window.localStorage.getItem(VIEW_KEY) === 'list' ? 'list' : 'grid'
  } catch {
    return 'grid'
  }
}

function writeView(view: ViewMode) {
  try {
    window.localStorage.setItem(VIEW_KEY, view)
  } catch {
    /* not remembered — fine */
  }
}

function StatsRow({ stats, isPending }: { stats?: ProjectStats; isPending: boolean }) {
  if (isPending) {
    return (
      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4" aria-hidden>
        {[0, 1, 2, 3].map((n) => <div key={n} className="card card-body h-[104px] animate-pulse" />)}
      </div>
    )
  }
  if (!stats) return null
  const trend = stats.projects_previous_month > 0 || stats.projects_this_month > 0
    ? {
      direction: stats.month_change_percent === null
        ? (stats.projects_this_month > 0 ? 'up' as const : 'stable' as const)
        : stats.month_change_percent > 0 ? 'up' as const : stats.month_change_percent < 0 ? 'down' as const : 'stable' as const,
      changePercent: stats.month_change_percent,
    }
    : undefined
  return (
    <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
      <StatCard label="Всего проектов" value={stats.total_projects} icon={FolderKanban} hint={stats.drafts ? `черновиков: ${stats.drafts}` : 'в портфолио'} />
      <StatCard label="Студентов с проектами" value={stats.active_students} icon={GraduationCap} hint="авторы работ" />
      <StatCard
        label="Проектов в этом месяце"
        value={stats.projects_this_month}
        icon={CalendarRange}
        trend={trend && trend.changePercent !== null ? trend : undefined}
        hint={trend && trend.changePercent !== null ? 'к прошлому месяцу' : `в прошлом: ${stats.projects_previous_month}`}
      />
      <StatCard label="Групп с проектами" value={stats.groups_with_projects} icon={Users} hint="участвуют в портфолио" />
    </div>
  )
}

function ViewToggle({ value, onChange }: { value: ViewMode; onChange: (view: ViewMode) => void }) {
  const options: { value: ViewMode; label: string; icon: typeof LayoutGrid }[] = [
    { value: 'grid', label: 'Плитка', icon: LayoutGrid },
    { value: 'list', label: 'Список', icon: List },
  ]
  return (
    <div role="radiogroup" aria-label="Вид" className="inline-flex h-10 items-center gap-1 rounded-lg border border-border bg-surface p-1">
      {options.map((option) => {
        const active = option.value === value
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={option.label}
            title={option.label}
            onClick={() => onChange(option.value)}
            className={cn(
              'flex h-full w-9 items-center justify-center rounded-md transition-colors',
              active ? 'bg-brand-50 text-brand-700' : 'text-ink-muted hover:bg-surface-hover hover:text-ink',
            )}
          >
            <option.icon className="size-4" aria-hidden />
          </button>
        )
      })}
    </div>
  )
}

export function ProjectsPage() {
  const base = useProjectsBase()
  const navigate = useNavigate()
  const { showToast } = useToast()
  const [params, setParams] = useSearchParams()
  const [view, setView] = useState<ViewMode>(readView)
  const [toDelete, setToDelete] = useState<ProjectListItem | null>(null)

  // Filters live in the URL, so a link (or Back) reopens the same view.
  const q = params.get('q') ?? ''
  const group = params.get('group') ?? ''
  const student = params.get('student') ?? ''
  const technology = params.get('technology') ?? ''
  const period = params.get('period') ?? ''
  const page = Math.max(1, Number(params.get('page')) || 1)
  const [search, setSearch] = useState(q)

  const update = (patch: Record<string, string>) => {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(patch)) {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    if (!('page' in patch)) next.delete('page')
    setParams(next, { replace: true })
  }

  // Debounce typing into the URL / request.
  useEffect(() => {
    if (search === q) return
    const id = window.setTimeout(() => update({ q: search.trim() }), 300)
    return () => window.clearTimeout(id)
  }, [search])

  const filters: ProjectFilters = useMemo(
    () => ({ q: q || undefined, group: group || undefined, student: student || undefined, technology: technology || undefined, ...periodRange(period), page }),
    [q, group, student, technology, period, page],
  )
  const hasFilters = Boolean(q || group || student || technology || period)

  const options = useProjectOptions()
  const stats = useProjectStats()
  const list = useProjects(filters)
  const remove = useDeleteProject()
  const canCreate = options.data?.can_create ?? false

  const changeView = (next: ViewMode) => {
    setView(next)
    writeView(next)
  }

  const confirmDelete = () => {
    if (!toDelete) return
    remove.mutate(toDelete.id, {
      onSuccess: () => {
        showToast(`Проект «${toDelete.title}» удалён`, 'success')
        setToDelete(null)
      },
      onError: (error) => showToast(extractErrorMessage(error, 'Не удалось удалить проект.'), 'error'),
    })
  }

  const cardProps = {
    base,
    onEdit: (project: ProjectListItem) => navigate(`${base}/${project.id}/edit`),
    onDelete: setToDelete,
  }

  const results = list.data?.results ?? []
  const showSkeleton = list.isPending

  return (
    <div>
      <PageHeader
        title="Проекты студентов"
        description="Управляйте работами студентов и показывайте их."
        actions={canCreate ? (
          <Button leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => navigate(`${base}/new`)}>
            Добавить проект
          </Button>
        ) : undefined}
      />

      <StatsRow stats={stats.data} isPending={stats.isPending} />

      {/* One row on desktop; on smaller screens search + view toggle, then the filters. */}
      <div className="mb-5 flex flex-wrap items-center gap-3 xl:flex-nowrap">
        <div className="order-1 min-w-0 flex-1 xl:w-80 xl:flex-none">
          <SearchInput value={search} onChange={setSearch} placeholder="Поиск по проекту, студенту, технологии…" aria-label="Поиск проектов" />
        </div>
        <div className="order-2 xl:order-4"><ViewToggle value={view} onChange={changeView} /></div>
        <div className="order-3 grid w-full min-w-0 grid-cols-2 gap-3 md:grid-cols-4 xl:w-auto xl:flex-1">
          <Select aria-label="Группа" placeholder="Все группы" value={group}
            onChange={(e) => update({ group: e.target.value })}
            options={(options.data?.groups ?? []).map((g) => ({ value: String(g.id), label: g.name }))} />
          <Select aria-label="Студент" placeholder="Все студенты" value={student}
            onChange={(e) => update({ student: e.target.value })}
            options={(options.data?.students ?? []).map((s) => ({ value: String(s.id), label: s.full_name }))} />
          <Select aria-label="Период" placeholder="За всё время" value={period}
            onChange={(e) => update({ period: e.target.value })} options={PERIOD_OPTIONS} />
          <Select aria-label="Технология" placeholder="Все технологии" value={technology}
            onChange={(e) => update({ technology: e.target.value })}
            options={(options.data?.technologies ?? []).map((t) => ({ value: t, label: t }))} />
        </div>
        {hasFilters ? (
          <Button variant="ghost" size="sm" className="order-4 xl:order-3" onClick={() => { setSearch(''); setParams({}, { replace: true }) }}>
            Сбросить
          </Button>
        ) : null}
      </div>

      {list.isError ? <ErrorState title="Не удалось загрузить проекты" onRetry={() => void list.refetch()} /> : null}

      {showSkeleton ? (
        view === 'grid' ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:gap-5 xl:grid-cols-3" role="status" aria-label="Загружаем проекты…">
            {Array.from({ length: 6 }, (_, n) => <ProjectCardSkeleton key={n} />)}
          </div>
        ) : (
          <div className="card divide-y divide-border" role="status" aria-label="Загружаем проекты…">
            {Array.from({ length: 5 }, (_, n) => <ProjectRowSkeleton key={n} />)}
          </div>
        )
      ) : null}

      {list.data && results.length === 0 ? (
        hasFilters ? (
          <div className="card flex flex-col items-center gap-3 border-dashed px-4 py-14 text-center">
            <span className="flex size-11 items-center justify-center rounded-full bg-surface-hover text-ink-muted"><SearchX className="size-5" aria-hidden /></span>
            <div>
              <p className="font-medium text-ink">Ничего не найдено</p>
              <p className="mt-1 text-sm text-ink-secondary">Попробуйте изменить запрос или сбросить фильтры.</p>
            </div>
            <Button variant="secondary" size="sm" onClick={() => { setSearch(''); setParams({}, { replace: true }) }}>Сбросить фильтры</Button>
          </div>
        ) : (
          <div className="card flex flex-col items-center gap-4 border-dashed px-4 py-14 text-center">
            <ProjectsIllustration className="h-28 w-auto" />
            <div>
              <p className="text-base font-semibold text-ink">Проектов пока нет</p>
              <p className="mx-auto mt-1 max-w-md text-sm text-ink-secondary">
                {canCreate
                  ? 'Студенты показывают вам свои работы — добавьте их сюда, чтобы собрать портфолио группы.'
                  : 'Когда тренеры добавят работы студентов, они появятся здесь.'}
              </p>
            </div>
            {canCreate ? (
              <Button leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => navigate(`${base}/new`)}>
                Добавить первый проект студента
              </Button>
            ) : null}
          </div>
        )
      ) : null}

      {results.length > 0 ? (
        <div className={cn('transition-opacity', list.isPlaceholderData && 'opacity-60')}>
          {view === 'grid' ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:gap-5 xl:grid-cols-3">
              {results.map((project) => <ProjectCard key={project.id} project={project} {...cardProps} />)}
            </div>
          ) : (
            <ul className="card divide-y divide-border overflow-hidden">
              {results.map((project) => <ProjectRow key={project.id} project={project} {...cardProps} />)}
            </ul>
          )}
          <div className="mt-4">
            <Pagination page={page} pageSize={PAGE_SIZE} totalCount={list.data?.count ?? 0} onPageChange={(next) => update({ page: String(next) })} />
          </div>
        </div>
      ) : null}

      <ConfirmDialog
        isOpen={toDelete !== null}
        title="Удалить проект?"
        message={toDelete ? `Проект «${toDelete.title}» и все его изображения будут удалены без возможности восстановления.` : ''}
        confirmLabel="Удалить"
        tone="danger"
        isLoading={remove.isPending}
        onConfirm={confirmDelete}
        onCancel={() => setToDelete(null)}
      />
    </div>
  )
}
