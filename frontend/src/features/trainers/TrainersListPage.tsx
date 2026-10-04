import { useState } from 'react'
import { UserCog } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { DataTable } from '@/components/ui/DataTable'
import type { DataTableColumn } from '@/components/ui/DataTable'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { LoadingState } from '@/components/ui/LoadingState'
import { SearchInput } from '@/components/ui/SearchInput'
import { Tabs } from '@/components/ui/Tabs'
import { KpiBadge, PeriodSelect, ReportPagination, pct, periodCaption } from '@/features/analytics/reportUi'
import { useReportTeachers } from '@/hooks/useReports'
import type { ReportPeriodKey, ReportTeacherRow } from '@/types/reports'

type View = 'all' | 'kpi' | 'load'

const TABS: { key: View; label: string }[] = [
  { key: 'all', label: 'Все тренеры' },
  { key: 'kpi', label: 'KPI' },
  { key: 'load', label: 'Нагрузка' },
]

const DEFAULT_SORT: Record<View, string> = { all: 'name', kpi: '-kpi', load: '-students' }

const nameColumn: DataTableColumn<ReportTeacherRow> = {
  key: 'name',
  header: 'Тренер',
  render: (row) => (
    <div className="min-w-0">
      <p className="font-medium text-ink">{row.name}</p>
      <p className="text-xs text-ink-secondary">{row.subjects.join(', ') || row.position}</p>
    </div>
  ),
}

const COLUMNS: Record<View, DataTableColumn<ReportTeacherRow>[]> = {
  all: [
    nameColumn,
    {
      key: 'groups',
      header: 'Группы',
      render: (row) => (row.groups.length ? row.groups.map((g) => g.name).join(', ') : '—'),
    },
    { key: 'students', header: 'Студентов', render: (row) => row.students.active },
    { key: 'status', header: 'Статус', render: (row) => <Badge tone={row.is_active ? 'success' : 'muted'}>{row.is_active ? 'Активен' : 'Неактивен'}</Badge> },
    { key: 'kpi', header: 'KPI', render: (row) => <KpiBadge value={row.kpi} level={row.kpi_level} /> },
  ],
  kpi: [
    nameColumn,
    { key: 'attendance', header: 'Посещаемость', render: (row) => pct(row.attendance_rate) },
    { key: 'homework', header: 'ДЗ', render: (row) => pct(row.homework_rate) },
    { key: 'progress', header: 'Результаты', render: (row) => pct(row.progress_rate) },
    { key: 'activity', header: 'Активность', render: (row) => pct(row.activity_rate) },
    { key: 'kpi', header: 'Общий KPI', render: (row) => <KpiBadge value={row.kpi} level={row.kpi_level} /> },
  ],
  load: [
    nameColumn,
    { key: 'groups', header: 'Групп', render: (row) => row.groups_count },
    { key: 'students', header: 'Студентов (активных)', render: (row) => `${row.students.total} (${row.students.active})` },
    { key: 'lessons', header: 'Занятий проведено', render: (row) => `${row.lessons.held} из ${row.lessons.total}` },
    { key: 'left', header: 'Ушли', render: (row) => row.students.left },
  ],
}

/** Team Lead / Admin: every trainer of the academy, with KPI and workload
 * for the chosen period (backend: GET /reports/teachers/). */
export function TrainersListPage() {
  const navigate = useNavigate()
  const [view, setView] = useState<View>('all')
  const [period, setPeriod] = useState<ReportPeriodKey>('this_month')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)

  const { data, isPending, isError, refetch } = useReportTeachers({
    period,
    q: search.trim() || undefined,
    sort: DEFAULT_SORT[view],
    page,
  })

  return (
    <div>
      <PageHeader title="Тренеры" description={periodCaption(data?.filters) || 'Все тренеры академии: группы, KPI и нагрузка'} />

      <Tabs
        aria-label="Разделы тренеров"
        items={TABS}
        value={view}
        onChange={(next) => {
          setView(next)
          setPage(1)
        }}
      />

      <FilterBar>
        <FilterField size="lg">
          <SearchInput
            value={search}
            onChange={(value) => {
              setSearch(value)
              setPage(1)
            }}
            placeholder="Поиск по имени, группе, предмету"
          />
        </FilterField>
        <FilterField>
          <PeriodSelect
            value={period}
            onChange={(value) => {
              setPeriod(value)
              setPage(1)
            }}
          />
        </FilterField>
      </FilterBar>

      {isPending ? <LoadingState label="Загружаем тренеров…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}

      {data && data.results.length === 0 ? (
        <EmptyState icon={UserCog} title="Тренеры не найдены" description="Измените поиск или период." />
      ) : null}

      {data && data.results.length > 0 ? (
        <div className="space-y-3">
          <DataTable
            columns={COLUMNS[view]}
            rows={data.results}
            getRowKey={(row) => row.id}
            onRowClick={(row) => navigate(`/app/trainers/${row.id}`)}
          />
          <ReportPagination page={data} onPageChange={setPage} />
        </div>
      ) : null}
    </div>
  )
}
