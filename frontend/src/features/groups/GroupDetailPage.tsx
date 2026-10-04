import { useMemo, useState } from 'react'
import { ClipboardList, Plus } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { HOMEWORK_ORDERING } from '@/api/homework'
import { LESSON_STATUS_TONE } from '@/components/academy/lessonStatus'
import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { DataTable } from '@/components/ui/DataTable'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { PageHeader } from '@/components/layout/PageHeader'
import { Tabs } from '@/components/ui/Tabs'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { useAttendanceList } from '@/hooks/useAttendance'
import { CreateSessionModal } from '@/features/exams/CreateSessionModal'
import { ExamCard } from '@/features/exams/ExamCard'
import { useExamList } from '@/hooks/useExams'
import { AcademicConfigSummary, GroupAcademicConfig } from './GroupAcademicConfig'
import { useAuth } from '@/hooks/useAuth'
import { useReportGroup } from '@/hooks/useReports'
import { seesWholeAcademy } from '@/lib/roles'
import { KpiBadge, PeriodSelect, pct, periodCaption } from '@/features/analytics/reportUi'
import type { ReportPeriodKey } from '@/types/reports'
import { useGroup, useGroupSchedule } from '@/hooks/useGroups'
import { useHomeworkList } from '@/hooks/useHomework'
import { useAnalyticsDashboard } from '@/hooks/useKPI'
import { useStudents } from '@/hooks/useStudents'
import { getKPIPeriods } from '@/features/kpi/periods'
import type { KPIPeriodKey } from '@/types/kpi'
import type { Group, GroupScheduleLesson } from '@/types/academy'
import { ATTENDANCE_STATUS_LABELS } from '@/types/attendance'
import { DAY_LABELS, WEEKDAY_ORDER } from '@/types/common'
import { cn } from '@/utils/cn'
import { formatDateShort, formatTimeRange } from '@/utils/format'

const STATUS_TONE: Record<Group['status'], BadgeTone> = {
  active: 'success',
  paused: 'warning',
  completed: 'muted',
  cancelled: 'danger',
}

const TABS = [
  { key: 'overview', label: 'Обзор' },
  { key: 'students', label: 'Студенты' },
  { key: 'schedule', label: 'Расписание' },
  { key: 'attendance', label: 'Посещаемость' },
  { key: 'homework', label: 'Домашние задания' },
  { key: 'kpi', label: 'KPI' },
  // Admin / Team Lead only: the group's test sessions (create one for this group).
  { key: 'sessions', label: 'Сессии' },
  // Admin / Team Lead only: every trainer of the group side by side (backend: /reports/groups/{id}/).
  { key: 'analytics', label: 'Аналитика' },
] as const

const ACADEMY_ONLY_TABS: readonly string[] = ['sessions', 'analytics']

type TabKey = (typeof TABS)[number]['key']

export function GroupDetailPage() {
  const { id } = useParams<{ id: string }>()
  const groupId = Number(id)
  const [tab, setTab] = useState<TabKey>('overview')
  const { user } = useAuth()
  const academyView = seesWholeAcademy(user?.role)
  const tabs = academyView
    ? TABS.map((item) => (item.key === 'overview' ? { ...item, label: 'Общая информация' } : item))
    : TABS.filter((item) => !ACADEMY_ONLY_TABS.includes(item.key))

  const { data: group, isPending, isError, refetch } = useGroup(groupId)

  if (isPending) return <LoadingState label="Загружаем группу…" />
  if (isError || !group) return <ErrorState onRetry={() => void refetch()} />

  return (
    <div>
      <PageHeader
        title={group.name}
        description={group.course_name}
        badge={<Badge tone={STATUS_TONE[group.status]}>{group.status_display}</Badge>}
      />

      <Tabs aria-label="Разделы группы" items={tabs} value={tab} onChange={setTab} />

      {tab === 'overview' ? (
        <OverviewTab group={group} linkTrainers={academyView} onEditSchedule={() => setTab('schedule')} />
      ) : null}
      {tab === 'students' ? <StudentsTab groupId={groupId} /> : null}
      {tab === 'schedule' ? (
        academyView ? (
          <div className="space-y-8">
            <GroupAcademicConfig groupId={groupId} />
            <div>
              <h3 className="section-title mb-4">Занятия по дням</h3>
              <ScheduleTab groupId={groupId} />
            </div>
          </div>
        ) : (
          <ScheduleTab groupId={groupId} />
        )
      ) : null}
      {tab === 'sessions' && academyView ? <SessionsTab groupId={groupId} /> : null}
      {tab === 'attendance' ? <AttendanceTab groupId={groupId} /> : null}
      {tab === 'homework' ? <HomeworkTab groupId={groupId} /> : null}
      {tab === 'kpi' ? <KpiTab groupId={groupId} /> : null}
      {tab === 'analytics' && academyView ? <AnalyticsTab groupId={groupId} /> : null}
    </div>
  )
}

function OverviewTab({ group, linkTrainers, onEditSchedule }: { group: Group; linkTrainers: boolean; onEditSchedule: () => void }) {
  return (
    <div className="space-y-6">
      <dl className="grid grid-cols-1 gap-4 card card-body sm:grid-cols-2">
        <Field label="Дата начала" value={formatDateShort(group.start_date)} />
        <Field label="Дата окончания" value={group.end_date ? formatDateShort(group.end_date) : '—'} />
        <Field label="Студентов" value={`${group.students_count}${group.max_students ? ` / ${group.max_students}` : ''}`} />
        <Field label="Учебных программ" value={`${group.teachers.length}`} />
        {group.description ? <Field label="Описание" value={group.description} className="sm:col-span-2" /> : null}
      </dl>

      {linkTrainers ? (
        <AcademicConfigSummary groupId={group.id} onEdit={onEditSchedule} />
      ) : (
      <div>
        <h3 className="section-title mb-4">Учебные программы</h3>
        {group.teachers.length === 0 ? (
          <EmptyState title="У группы пока нет учебных программ" />
        ) : (
          <div className="space-y-3">
            {group.teachers.map((program) => {
              const activeSlots = program.schedules.filter((slot) => slot.is_active)
              return (
                <div key={program.id} className="card card-body">
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-medium text-ink">
                      {linkTrainers ? (
                        <Link to={`/app/trainers/${program.teacher}`} className="text-brand-700 hover:underline">
                          {program.teacher_detail.user.first_name} {program.teacher_detail.user.last_name}
                        </Link>
                      ) : (
                        <>
                          {program.teacher_detail.user.first_name} {program.teacher_detail.user.last_name}
                        </>
                      )}
                      {program.subject_detail ? ` — ${program.subject_detail.name}` : ''}
                    </p>
                    <Badge tone={program.is_active ? 'success' : 'muted'}>{program.is_active ? 'Активна' : 'Неактивна'}</Badge>
                  </div>
                  <ul className="mt-2 space-y-1 text-sm text-ink-secondary">
                    {activeSlots.length === 0 ? (
                      <li>Нет активных слотов расписания</li>
                    ) : (
                      activeSlots.map((slot) => (
                        <li key={slot.id}>
                          {slot.day_of_week_label} {formatTimeRange(slot.start_time, slot.end_time)}
                          {slot.room_name ? ` · ${slot.room_name}` : ''}
                        </li>
                      ))
                    )}
                  </ul>
                </div>
              )
            })}
          </div>
        )}
      </div>
      )}
    </div>
  )
}

function Field({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div className={className}>
      <dt className="text-sm text-ink-secondary">{label}</dt>
      <dd className="mt-0.5 font-medium text-ink">{value}</dd>
    </div>
  )
}

function StudentsTab({ groupId }: { groupId: number }) {
  const navigate = useNavigate()
  const { data, isPending, isError, refetch } = useStudents({ group: groupId })

  if (isPending) return <LoadingState label="Загружаем студентов…" />
  if (isError) return <ErrorState onRetry={() => void refetch()} />
  if (data.results.length === 0) return <EmptyState title="В группе пока нет студентов" />

  return (
    <DataTable
      getRowKey={(student) => student.id}
      rows={data.results}
      onRowClick={(student) => navigate(`/app/students/${student.id}`)}
      columns={[
        { key: 'name', header: 'Имя', render: (student) => student.full_name },
        { key: 'phone', header: 'Телефон', render: (student) => student.phone || '—' },
        {
          key: 'status',
          header: 'Статус',
          render: (student) => <Badge tone={student.is_active ? 'success' : 'muted'}>{student.is_active ? 'Активен' : 'Неактивен'}</Badge>,
        },
      ]}
    />
  )
}

/** The group's schedule, grouped by weekday (Пн/Чт/Пт-style) rather than a
 * flat reverse-chronological Lesson list — a Trainer opens a group to see
 * *when* it meets and what's coming up on each of those days, not to hunt
 * through every Lesson ever generated for it. */
function ScheduleTab({ groupId }: { groupId: number }) {
  const { data, isPending, isError, refetch } = useGroupSchedule(groupId)

  if (isPending) return <LoadingState label="Загружаем расписание…" />
  if (isError) return <ErrorState onRetry={() => void refetch()} />
  if (data.lessons.length === 0) {
    return <EmptyState title="Занятий пока нет" description="Занятия создаются автоматически после того, как у курса группы готов план занятий." />
  }

  const byWeekday = new Map<string, GroupScheduleLesson[]>()
  for (const lesson of data.lessons) {
    const bucket = byWeekday.get(lesson.weekday)
    if (bucket) bucket.push(lesson)
    else byWeekday.set(lesson.weekday, [lesson])
  }
  const weekdays = WEEKDAY_ORDER.filter((day) => byWeekday.has(day))

  return (
    <div className="space-y-6">
      {weekdays.map((day) => {
        const lessons = byWeekday.get(day) ?? []
        return (
          <div key={day}>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-secondary">
              {lessons[0]?.weekday_label ?? DAY_LABELS[day]}
            </h3>
            <ul className="space-y-2">
              {lessons.map((lesson) => (
                <li key={lesson.id}>
                  <Link
                    to={`/app/lessons/${lesson.id}`}
                    className={cn(
                      'flex flex-wrap items-center justify-between gap-2 card card-interactive px-4 py-3',
                      lesson.status === 'cancelled' && 'opacity-70',
                    )}
                  >
                    <div>
                      <p className="text-sm font-medium text-ink">
                        {formatTimeRange(lesson.start_time, lesson.end_time)}
                        <span className="ml-2 font-normal text-ink-secondary">
                          {formatDateShort(lesson.date)} · Занятие {lesson.lesson_number}
                        </span>
                      </p>
                      <p className="mt-0.5 text-sm text-ink-secondary">
                        {lesson.subject_name ?? 'Без предмета'}
                        {lesson.topic ? ` — ${lesson.topic}` : ''}
                      </p>
                      {lesson.room_name ? <p className="mt-0.5 text-xs text-ink-muted">Аудитория: {lesson.room_name}</p> : null}
                    </div>
                    <Badge tone={LESSON_STATUS_TONE[lesson.status]}>{lesson.status_display}</Badge>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )
      })}
    </div>
  )
}

function AttendanceTab({ groupId }: { groupId: number }) {
  const { data, isPending, isError, refetch } = useAttendanceList({ group: groupId, ordering: '-lesson__date' })

  if (isPending) return <LoadingState label="Загружаем посещаемость…" />
  if (isError) return <ErrorState onRetry={() => void refetch()} />
  if (data.results.length === 0) return <EmptyState title="Посещаемость ещё не отмечалась" />

  return (
    <DataTable
      getRowKey={(record) => record.id ?? `${record.student}-${record.lesson}`}
      rows={data.results}
      columns={[
        { key: 'date', header: 'Дата', render: (record) => formatDateShort(record.lesson_date) },
        { key: 'student', header: 'Студент', render: (record) => record.student_name },
        {
          key: 'status',
          header: 'Статус',
          render: (record) => (record.status ? <Badge tone={record.status === 'present' ? 'success' : record.status === 'absent' ? 'danger' : 'warning'}>{ATTENDANCE_STATUS_LABELS[record.status]}</Badge> : '—'),
        },
      ]}
    />
  )
}

function HomeworkTab({ groupId }: { groupId: number }) {
  const { data, isPending, isError, refetch } = useHomeworkList({ group: groupId, ordering: HOMEWORK_ORDERING })

  if (isPending) return <LoadingState label="Загружаем домашние задания…" />
  if (isError) return <ErrorState onRetry={() => void refetch()} />
  if (data.results.length === 0) return <EmptyState title="Домашних заданий пока нет" />

  return (
    <ul className="space-y-2">
      {data.results.map((homework) => (
        <li key={homework.id}>
          <Link to={`/app/homework/${homework.id}`} className="flex items-center justify-between card card-interactive px-4 py-3">
            <span className="text-sm font-medium text-ink">{homework.title}</span>
            <span className="text-sm text-ink-secondary">{homework.results_count} результатов</span>
          </Link>
        </li>
      ))}
    </ul>
  )
}

/** Computed live from this group's own Lesson/Attendance/HomeworkResult
 * records for the chosen period — nothing stored, nothing to recalculate. */
function KpiTab({ groupId }: { groupId: number }) {
  const [periodKey, setPeriodKey] = useState<KPIPeriodKey>('this_month')
  const periods = useMemo(() => getKPIPeriods(), [])
  const period = periods.find((item) => item.key === periodKey) ?? periods[0]

  const { data, isPending, isError, refetch } = useAnalyticsDashboard({
    period: periodKey,
    start_date: period.dateFrom,
    end_date: period.dateTo,
    group: groupId,
  })

  if (isPending) return <LoadingState label="Считаем KPI…" />
  if (isError) return <ErrorState onRetry={() => void refetch()} />

  // Any lesson in the period, whatever its status — not `lessons_scheduled`,
  // which is only still-open lessons and reads 0 once they're all completed.
  const hasData = data.lessons.lessons_total.value > 0

  return (
    <div>
      <SegmentedControl<KPIPeriodKey>
        aria-label="Период"
        className="mb-4"
        value={periodKey}
        onChange={setPeriodKey}
        options={periods.map((item) => ({ value: item.key, label: item.label }))}
      />

      {!hasData ? (
        <EmptyState title="Нет данных за выбранный период" />
      ) : (
        <div className="card card-body">
          <p className="text-sm font-medium text-ink">
            {formatDateShort(period.dateFrom)} — {formatDateShort(period.dateTo)}
          </p>
          <div className="mt-3 grid grid-cols-1 gap-3 text-sm min-[400px]:grid-cols-2 sm:grid-cols-3">
            <Field
              label="Занятий"
              value={`${data.lessons.lessons_total.value} (${data.lessons.lessons_completed.value} проведено)`}
            />
            <Field label="Посещаемость" value={`${data.attendance.attendance_rate.value}%`} />
            <Field label="Выполнение ДЗ" value={`${data.homework.submission_rate.value}%`} />
            <Field label="Средний балл" value={`${data.homework.average_score.value}/10`} />
          </div>
        </div>
      )}
    </div>
  )
}

/** Group → Trainers / Students results / KPI for a period, read-only. */
function AnalyticsTab({ groupId }: { groupId: number }) {
  const navigate = useNavigate()
  const [period, setPeriod] = useState<ReportPeriodKey>('this_month')
  const { data, isPending, isError, refetch } = useReportGroup(groupId, { period, page_size: 200 })

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <p className="text-sm text-ink-secondary">{periodCaption(data?.filters)}</p>
        <div className="w-full sm:w-52">
          <PeriodSelect value={period} onChange={setPeriod} />
        </div>
      </div>

      {isPending ? <LoadingState label="Считаем показатели…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}

      {data ? (
        <>
          <dl className="grid grid-cols-2 gap-4 card card-body sm:grid-cols-5">
            <Field label="Посещаемость" value={pct(data.metrics.attendance ?? null)} />
            <Field label="ДЗ" value={pct(data.metrics.homework ?? null)} />
            <Field label="Результаты" value={pct(data.metrics.progress ?? null)} />
            <Field label="Активность" value={pct(data.metrics.lesson_completion ?? null)} />
            <div>
              <dt className="text-xs text-ink-secondary">KPI</dt>
              <dd className="mt-1">
                <KpiBadge value={data.kpi.total} level={data.kpi.status} />
              </dd>
            </div>
          </dl>

          <div>
            <h3 className="section-title mb-3">Тренеры группы</h3>
            {data.teacher_breakdown.length === 0 ? (
              <EmptyState title="Нет занятий за период" />
            ) : (
              <DataTable
                rows={data.teacher_breakdown}
                getRowKey={(row) => row.id ?? 'none'}
                onRowClick={(row) => (row.id ? navigate(`/app/trainers/${row.id}`) : undefined)}
                columns={[
                  { key: 'name', header: 'Тренер', render: (row) => row.name },
                  { key: 'lessons', header: 'Занятий', render: (row) => `${row.lessons.held} / ${row.lessons.total}` },
                  { key: 'attendance', header: 'Посещаемость', render: (row) => pct(row.attendance_rate) },
                  { key: 'homework', header: 'ДЗ', render: (row) => pct(row.homework_rate) },
                  { key: 'kpi', header: 'KPI', render: (row) => <KpiBadge value={row.kpi} level={row.kpi_level} /> },
                ]}
              />
            )}
          </div>

          <div>
            <h3 className="section-title mb-3">Студенты</h3>
            {data.students_list.results.length === 0 ? (
              <EmptyState title="В группе нет студентов" />
            ) : (
              <DataTable
                rows={data.students_list.results}
                getRowKey={(row) => row.id}
                onRowClick={(row) => navigate(`/app/students/${row.id}`)}
                columns={[
                  { key: 'name', header: 'Студент', render: (row) => row.name },
                  { key: 'attendance', header: 'Посещаемость', render: (row) => pct(row.attendance_rate) },
                  { key: 'homework', header: 'ДЗ', render: (row) => pct(row.homework_rate) },
                  { key: 'score', header: 'Средний балл', render: (row) => row.average_score ?? '—' },
                  { key: 'progress', header: 'Прогресс', render: (row) => pct(row.progress_rate) },
                ]}
              />
            )}
          </div>
        </>
      ) : null}
    </div>
  )
}

/** The group's test sessions + «Создать сессию» for this group (its trainer
 * and the test's subject are filled in by the backend). */
function SessionsTab({ groupId }: { groupId: number }) {
  const [isCreateOpen, setCreateOpen] = useState(false)
  const { data, isPending, isError, refetch } = useExamList({ group: groupId })
  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setCreateOpen(true)}>
          Создать сессию
        </Button>
      </div>
      {isPending ? <LoadingState label="Загружаем сессии…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}
      {data && data.results.length === 0 ? <EmptyState icon={ClipboardList} title="У группы пока нет тестовых сессий" /> : null}
      {data && data.results.length > 0 ? (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {data.results.map((session) => (
            <ExamCard key={session.id} session={session} />
          ))}
        </div>
      ) : null}
      <CreateSessionModal isOpen={isCreateOpen} onClose={() => setCreateOpen(false)} initialGroup={groupId} />
    </div>
  )
}
