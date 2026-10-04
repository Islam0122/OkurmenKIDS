import { useState } from 'react'
import { BookOpen, CalendarCheck, ClipboardCheck, GraduationCap, NotebookPen, Users } from 'lucide-react'
import { useNavigate, useParams } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { BackLink } from '@/components/ui/BackLink'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { DataTable } from '@/components/ui/DataTable'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { LoadingState } from '@/components/ui/LoadingState'
import { StatCard } from '@/components/ui/StatCard'
import { StatGrid } from '@/components/ui/StatGrid'
import { KpiBadge, PeriodSelect, pct, periodCaption } from '@/features/analytics/reportUi'
import { KPI_STATUS_CARD_TONE } from '@/features/kpi/kpiStatus'
import { useReportTeacher } from '@/hooks/useReports'
import type { ReportPeriodKey } from '@/types/reports'
import { formatDate } from '@/utils/format'
import { ResultsOverview, ResultsTable } from '@/features/results/resultsUi'

/** Trainer → profile, KPI, workload, groups (→ Group → Students → results).
 * Read-only; backend: GET /reports/teachers/{id}/ (Admin / Team Lead). */
export function TrainerDetailPage() {
  const { id } = useParams<{ id: string }>()
  const teacherId = Number(id)
  const navigate = useNavigate()
  const [period, setPeriod] = useState<ReportPeriodKey>('this_month')
  const { data, isPending, isError, refetch } = useReportTeacher(teacherId, { period })

  if (isPending) return <LoadingState label="Загружаем тренера…" />
  if (isError || !data) return <ErrorState onRetry={() => void refetch()} />

  const { teacher } = data
  const metric = (key: string) => data.metrics[key] ?? null

  return (
    <div>
      <BackLink to="/app/trainers">Все тренеры</BackLink>
      <PageHeader
        title={teacher.name}
        description={periodCaption(data.filters)}
        badge={<Badge tone={teacher.is_active ? 'success' : 'muted'}>{teacher.is_active ? 'Активен' : 'Неактивен'}</Badge>}
      />

      <FilterBar>
        <FilterField label="Период">
          <PeriodSelect value={period} onChange={setPeriod} />
        </FilterField>
      </FilterBar>

      <div className="space-y-6">
        <section aria-label="KPI тренера">
          <StatGrid columns={4}>
            <StatCard label="Посещаемость" value={pct(metric('attendance'))} icon={CalendarCheck} />
            <StatCard label="Выполнение ДЗ" value={pct(metric('homework'))} icon={NotebookPen} />
            <StatCard label="Результаты студентов" value={pct(metric('progress'))} icon={GraduationCap} />
            <StatCard label="Активность (проведено занятий)" value={pct(metric('lesson_completion'))} icon={ClipboardCheck} />
          </StatGrid>
          <div className="mt-4 card card-body flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm text-ink-secondary">Общий KPI</p>
              <p className="text-2xl font-semibold text-ink">{pct(data.kpi.total)}</p>
            </div>
            <KpiBadge value={null} level={data.kpi.status} />
          </div>
        </section>

        <section aria-label="Нагрузка">
          <h2 className="section-title mb-3">Нагрузка</h2>
          <StatGrid columns={4}>
            <StatCard label="Групп" value={data.groups.length} icon={Users} />
            <StatCard label="Студентов (активных)" value={`${data.students.total} (${data.students.active})`} icon={GraduationCap} />
            <StatCard label="Занятий проведено" value={`${data.lessons.held} из ${data.lessons.total}`} icon={BookOpen} />
            <StatCard
              label="Отменено занятий"
              value={data.lessons.cancelled}
              icon={CalendarCheck}
              tone={data.lessons.cancelled > 0 ? KPI_STATUS_CARD_TONE.attention : 'default'}
            />
          </StatGrid>
        </section>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <Card title="Профиль" className="lg:col-span-1">
            <dl className="space-y-2 text-sm">
              <ProfileRow label="Должность" value={teacher.position || '—'} />
              <ProfileRow label="Email" value={teacher.email || '—'} />
              <ProfileRow label="Телефон" value={teacher.phone || '—'} />
              <ProfileRow label="Начало работы" value={teacher.hire_date ? formatDate(teacher.hire_date) : '—'} />
              <ProfileRow label="Предметы" value={data.subjects.join(', ') || '—'} />
            </dl>
          </Card>

          <Card title="Результаты по группам" className="lg:col-span-2" padding="none">
            {data.group_performance.length === 0 ? (
              <div className="card-body">
                <EmptyState icon={Users} title="Нет групп за период" />
              </div>
            ) : (
              <DataTable
                rows={data.group_performance}
                getRowKey={(row) => row.id}
                onRowClick={(row) => navigate(`/app/groups/${row.id}`)}
                columns={[
                  { key: 'name', header: 'Группа', render: (row) => <span className="font-medium text-ink">{row.name}</span> },
                  { key: 'students', header: 'Студентов', render: (row) => row.students.active },
                  { key: 'attendance', header: 'Посещаемость', render: (row) => pct(row.attendance_rate) },
                  { key: 'homework', header: 'ДЗ', render: (row) => pct(row.homework_rate) },
                  { key: 'progress', header: 'Результаты', render: (row) => pct(row.progress_rate) },
                  { key: 'kpi', header: 'KPI', render: (row) => <KpiBadge value={row.kpi} level={row.kpi_level} /> },
                ]}
              />
            )}
          </Card>
        </div>

        <section aria-label="Посещаемость и ДЗ">
          <h2 className="section-title mb-3">Посещаемость и домашние задания</h2>
          <StatGrid columns={4}>
            <StatCard label="Присутствовали" value={data.attendance.present + data.attendance.late} hint={`из ${data.attendance.total} отметок`} />
            <StatCard label="Пропуски" value={data.attendance.absent} tone={data.attendance.absent > 0 ? 'warning' : 'default'} />
            <StatCard label="ДЗ сдано" value={data.homework.submitted} hint={`из ${data.homework.results} результатов`} />
            <StatCard label="Средний балл ДЗ" value={data.homework.average_score ?? '—'} />
          </StatGrid>
        </section>

        <ResultsOverview filters={{ teacher: String(teacherId) }} />
        <ResultsTable filters={{ teacher: String(teacherId) }} columns={['student', 'group', 'test', 'subject']} title="Последние результаты учеников" />
      </div>
    </div>
  )
}

function ProfileRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-ink-secondary">{label}</dt>
      <dd className="text-right text-ink">{value}</dd>
    </div>
  )
}
