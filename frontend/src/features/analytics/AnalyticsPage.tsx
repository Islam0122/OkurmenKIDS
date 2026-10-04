import { useState } from 'react'
import { BookOpen, CalendarCheck, GraduationCap, LineChart, NotebookPen, UserCog, Users } from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { DataTable } from '@/components/ui/DataTable'
import type { DataTableColumn } from '@/components/ui/DataTable'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { LoadingState } from '@/components/ui/LoadingState'
import { SearchInput } from '@/components/ui/SearchInput'
import { StatCard } from '@/components/ui/StatCard'
import { StatGrid } from '@/components/ui/StatGrid'
import { Tabs } from '@/components/ui/Tabs'
import { KPI_STATUS_BADGE_TONE } from '@/features/kpi/kpiStatus'
import {
  useReportGroups,
  useReportOverview,
  useReportStudents,
  useReportSubjects,
  useReportTeachers,
} from '@/hooks/useReports'
import type {
  ReportGroupRow,
  ReportPage,
  ReportParams,
  ReportPeriodKey,
  ReportStudentRow,
  ReportSubjectRow,
  ReportTeacherRow,
} from '@/types/reports'

import { TestPerformanceReport } from '@/features/results/TestPerformanceReport'
import { KPI_LEVEL_LABEL, KpiBadge, PeriodSelect, ReportExportButtons, ReportPagination, pct, periodCaption } from './reportUi'

type Section = 'teachers' | 'groups' | 'students' | 'subjects' | 'tests'

const TABS: { key: Section; label: string }[] = [
  { key: 'teachers', label: 'Тренеры' },
  { key: 'groups', label: 'Группы' },
  { key: 'students', label: 'Студенты' },
  { key: 'subjects', label: 'Предметы' },
  { key: 'tests', label: 'Тесты' },
]

function isSection(value: string | null): value is Section {
  return TABS.some((tab) => tab.key === value)
}

const TEACHER_COLUMNS: DataTableColumn<ReportTeacherRow>[] = [
  { key: 'name', header: 'Тренер', render: (row) => <span className="font-medium text-ink">{row.name}</span> },
  { key: 'groups', header: 'Групп', render: (row) => row.groups_count },
  { key: 'students', header: 'Студентов', render: (row) => row.students.active },
  { key: 'attendance', header: 'Посещаемость', render: (row) => pct(row.attendance_rate) },
  { key: 'homework', header: 'ДЗ', render: (row) => pct(row.homework_rate) },
  { key: 'progress', header: 'Результаты', render: (row) => pct(row.progress_rate) },
  { key: 'load', header: 'Нагрузка (занятий)', render: (row) => `${row.lessons.held} / ${row.lessons.total}` },
  { key: 'kpi', header: 'KPI', render: (row) => <KpiBadge value={row.kpi} level={row.kpi_level} /> },
]

const GROUP_COLUMNS: DataTableColumn<ReportGroupRow>[] = [
  {
    key: 'name',
    header: 'Группа',
    render: (row) => (
      <div>
        <p className="font-medium text-ink">{row.name}</p>
        <p className="text-xs text-ink-secondary">{row.program}</p>
      </div>
    ),
  },
  { key: 'teacher', header: 'Тренер', render: (row) => row.teacher_names },
  { key: 'students', header: 'Студентов', render: (row) => row.students.active },
  { key: 'attendance', header: 'Посещаемость', render: (row) => pct(row.attendance_rate) },
  { key: 'homework', header: 'ДЗ', render: (row) => pct(row.homework_rate) },
  { key: 'progress', header: 'Средний результат', render: (row) => pct(row.progress_rate) },
  { key: 'activity', header: 'Активность', render: (row) => pct(row.activity_rate) },
  { key: 'kpi', header: 'KPI', render: (row) => <KpiBadge value={row.kpi} level={row.kpi_level} /> },
]

const STUDENT_COLUMNS: DataTableColumn<ReportStudentRow>[] = [
  { key: 'name', header: 'Студент', render: (row) => <span className="font-medium text-ink">{row.name}</span> },
  { key: 'group', header: 'Группа', render: (row) => row.group },
  { key: 'attendance', header: 'Посещаемость', render: (row) => pct(row.attendance_rate) },
  { key: 'homework', header: 'ДЗ', render: (row) => pct(row.homework_rate) },
  { key: 'score', header: 'Средний балл', render: (row) => row.average_score ?? '—' },
  { key: 'progress', header: 'Прогресс', render: (row) => pct(row.progress_rate) },
  { key: 'level', header: 'Уровень', render: (row) => <Badge tone={KPI_STATUS_BADGE_TONE[row.level]}>{KPI_LEVEL_LABEL[row.level]}</Badge> },
]

const SUBJECT_COLUMNS: DataTableColumn<ReportSubjectRow>[] = [
  { key: 'name', header: 'Предмет', render: (row) => <span className="font-medium text-ink">{row.name}</span> },
  { key: 'teachers', header: 'Тренеры', render: (row) => row.teacher_names },
  { key: 'groups', header: 'Групп', render: (row) => row.groups_count },
  { key: 'attendance', header: 'Посещаемость', render: (row) => pct(row.attendance_rate) },
  { key: 'activity', header: 'Активность', render: (row) => pct(row.activity_rate) },
  { key: 'score', header: 'Средний балл', render: (row) => row.average_score ?? '—' },
  { key: 'progress', header: 'Результаты', render: (row) => pct(row.progress_rate) },
  { key: 'kpi', header: 'KPI', render: (row) => <KpiBadge value={row.kpi} level={row.kpi_level} /> },
]

/** Team Lead / Admin analytics: by trainers, groups, students and subjects
 * for one period, plus the full report as PDF/Excel. Backend: /reports/*
 * (services.reports, the one KPI engine — no second KPI system). */
export function AnalyticsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const rawSection = searchParams.get('tab')
  const section: Section = isSection(rawSection) ? rawSection : 'teachers'
  const [period, setPeriod] = useState<ReportPeriodKey>('this_month')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)

  const base: ReportParams = { period }
  const tableParams: ReportParams = { period, q: search.trim() || undefined, page }
  const overview = useReportOverview(base)

  return (
    <div>
      <PageHeader
        title="Аналитика"
        description={periodCaption(overview.data?.filters) || 'Тренеры, группы, студенты и предметы академии'}
        actions={<ReportExportButtons params={base} />}
      />

      <FilterBar>
        <FilterField label="Период">
          <PeriodSelect
            value={period}
            onChange={(value) => {
              setPeriod(value)
              setPage(1)
            }}
          />
        </FilterField>
        <FilterField size="lg" label="Поиск">
          <SearchInput
            value={search}
            onChange={(value) => {
              setSearch(value)
              setPage(1)
            }}
          />
        </FilterField>
      </FilterBar>

      {overview.data ? (
        <StatGrid columns={4} className="mb-6">
          <StatCard label="Тренеров" value={overview.data.teachers.total} icon={UserCog} />
          <StatCard label="Групп (активных)" value={`${overview.data.groups.total} (${overview.data.groups.active})`} icon={Users} />
          <StatCard label="Студентов (активных)" value={`${overview.data.students.total} (${overview.data.students.active})`} icon={GraduationCap} />
          <StatCard label="Общий KPI" value={pct(overview.data.kpi.total)} icon={LineChart} />
          <StatCard label="Посещаемость" value={pct(overview.data.attendance.rate)} icon={CalendarCheck} />
          <StatCard label="Выполнение ДЗ" value={pct(overview.data.homework.completion_rate)} icon={NotebookPen} />
          <StatCard label="Средний балл ДЗ" value={overview.data.homework.average_score ?? '—'} icon={GraduationCap} />
          <StatCard label="Занятий проведено" value={`${overview.data.lessons.held} / ${overview.data.lessons.total}`} icon={BookOpen} />
        </StatGrid>
      ) : null}

      <Tabs
        aria-label="Разделы аналитики"
        items={TABS}
        value={section}
        onChange={(next) => {
          setSearchParams({ tab: next }, { replace: true })
          setPage(1)
        }}
      />

      {section === 'teachers' ? <TeachersSection params={tableParams} onPage={setPage} /> : null}
      {section === 'groups' ? <GroupsSection params={tableParams} onPage={setPage} /> : null}
      {section === 'students' ? <StudentsSection params={tableParams} onPage={setPage} /> : null}
      {section === 'subjects' ? <SubjectsSection params={tableParams} onPage={setPage} /> : null}
      {section === 'tests' ? <TestPerformanceReport /> : null}
    </div>
  )
}

interface SectionProps {
  params: ReportParams
  onPage: (page: number) => void
}

function TeachersSection({ params, onPage }: SectionProps) {
  const navigate = useNavigate()
  const query = useReportTeachers({ ...params, sort: '-kpi' })
  return (
    <ReportTable query={query} columns={TEACHER_COLUMNS} onPage={onPage} onRowClick={(row) => navigate(`/app/trainers/${row.id}`)} />
  )
}

function GroupsSection({ params, onPage }: SectionProps) {
  const navigate = useNavigate()
  const query = useReportGroups({ ...params, sort: '-kpi' })
  return <ReportTable query={query} columns={GROUP_COLUMNS} onPage={onPage} onRowClick={(row) => navigate(`/app/groups/${row.id}`)} />
}

function StudentsSection({ params, onPage }: SectionProps) {
  const navigate = useNavigate()
  const query = useReportStudents(params)
  return <ReportTable query={query} columns={STUDENT_COLUMNS} onPage={onPage} onRowClick={(row) => navigate(`/app/students/${row.id}`)} />
}

function SubjectsSection({ params, onPage }: SectionProps) {
  const query = useReportSubjects({ ...params, sort: '-kpi' })
  return <ReportTable query={query} columns={SUBJECT_COLUMNS} onPage={onPage} />
}

interface ReportTableProps<T extends { id: number }> {
  query: { data: ReportPage<T> | undefined; isPending: boolean; isError: boolean; refetch: () => unknown }
  columns: DataTableColumn<T>[]
  onPage: (page: number) => void
  onRowClick?: (row: T) => void
}

function ReportTable<T extends { id: number }>({ query, columns, onPage, onRowClick }: ReportTableProps<T>) {
  if (query.isPending) return <LoadingState label="Считаем показатели…" />
  if (query.isError || !query.data) return <ErrorState onRetry={() => void query.refetch()} />
  if (query.data.results.length === 0) return <EmptyState icon={LineChart} title="Нет данных за период" />
  return (
    <div className="space-y-3">
      <DataTable columns={columns} rows={query.data.results} getRowKey={(row) => row.id} onRowClick={onRowClick} />
      <ReportPagination page={query.data} onPageChange={onPage} />
    </div>
  )
}
