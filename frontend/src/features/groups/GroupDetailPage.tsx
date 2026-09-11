import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { DataTable } from '@/components/ui/DataTable'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAttendanceList } from '@/hooks/useAttendance'
import { useGroup, useGroupSchedule } from '@/hooks/useGroups'
import { useHomeworkList } from '@/hooks/useHomework'
import { useAnalyticsDashboard } from '@/hooks/useKPI'
import { useStudents } from '@/hooks/useStudents'
import { getKPIPeriods } from '@/features/kpi/periods'
import type { KPIPeriodKey } from '@/types/kpi'
import type { Group, GroupScheduleLesson, LessonStatus } from '@/types/academy'
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

const LESSON_STATUS_TONE: Record<LessonStatus, BadgeTone> = {
  planned: 'muted',
  completed: 'success',
  cancelled: 'danger',
}

const TABS = [
  { key: 'overview', label: 'Обзор' },
  { key: 'students', label: 'Студенты' },
  { key: 'schedule', label: 'Расписание' },
  { key: 'attendance', label: 'Посещаемость' },
  { key: 'homework', label: 'Домашние задания' },
  { key: 'kpi', label: 'KPI' },
] as const

type TabKey = (typeof TABS)[number]['key']

export function GroupDetailPage() {
  const { id } = useParams<{ id: string }>()
  const groupId = Number(id)
  const [tab, setTab] = useState<TabKey>('overview')

  const { data: group, isPending, isError, refetch } = useGroup(groupId)

  if (isPending) return <LoadingState label="Загружаем группу…" />
  if (isError || !group) return <ErrorState onRetry={() => void refetch()} />

  return (
    <div>
      <PageHeader
        title={group.name}
        description={group.course_name}
        actions={<Badge tone={STATUS_TONE[group.status]}>{group.status_display}</Badge>}
      />

      <div className="mb-6 flex gap-1 overflow-x-auto border-b border-border">
        {TABS.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setTab(item.key)}
            className={cn(
              'shrink-0 border-b-2 px-3 py-2.5 text-sm font-medium',
              tab === item.key ? 'border-brand-500 text-brand-700' : 'border-transparent text-ink-secondary hover:text-ink',
            )}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === 'overview' ? <OverviewTab group={group} /> : null}
      {tab === 'students' ? <StudentsTab groupId={groupId} /> : null}
      {tab === 'schedule' ? <ScheduleTab groupId={groupId} /> : null}
      {tab === 'attendance' ? <AttendanceTab groupId={groupId} /> : null}
      {tab === 'homework' ? <HomeworkTab groupId={groupId} /> : null}
      {tab === 'kpi' ? <KpiTab groupId={groupId} /> : null}
    </div>
  )
}

function OverviewTab({ group }: { group: Group }) {
  const days = group.days_of_week.map((day) => DAY_LABELS[day]).join(' / ')

  return (
    <dl className="grid grid-cols-1 gap-4 rounded-xl border border-border bg-surface p-5 sm:grid-cols-2">
      <Field label="Тренер" value={group.teacher_name} />
      <Field label="Аудитория" value={group.room_name ?? '—'} />
      <Field label="Дни занятий" value={days || '—'} />
      <Field label="Время" value={formatTimeRange(group.start_time, group.end_time)} />
      <Field label="Дата начала" value={formatDateShort(group.start_date)} />
      <Field label="Дата окончания" value={group.end_date ? formatDateShort(group.end_date) : '—'} />
      <Field label="Студентов" value={`${group.students_count}${group.max_students ? ` / ${group.max_students}` : ''}`} />
      {group.description ? <Field label="Описание" value={group.description} className="sm:col-span-2" /> : null}
    </dl>
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
    <div className="space-y-5">
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
                      'flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-surface px-4 py-3 hover:bg-surface-hover',
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
  const { data, isPending, isError, refetch } = useHomeworkList({ group: groupId, ordering: '-created_at' })

  if (isPending) return <LoadingState label="Загружаем домашние задания…" />
  if (isError) return <ErrorState onRetry={() => void refetch()} />
  if (data.results.length === 0) return <EmptyState title="Домашних заданий пока нет" />

  return (
    <ul className="space-y-2">
      {data.results.map((homework) => (
        <li key={homework.id}>
          <Link to={`/app/homework/${homework.id}`} className="flex items-center justify-between rounded-lg border border-border bg-surface px-4 py-3 hover:bg-surface-hover">
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

  const hasData = data.lessons.lessons_scheduled.value > 0

  return (
    <div>
      <div className="mb-4 flex flex-wrap gap-2">
        {periods.map((item) => (
          <Button
            key={item.key}
            variant={item.key === periodKey ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => setPeriodKey(item.key)}
          >
            {item.label}
          </Button>
        ))}
      </div>

      {!hasData ? (
        <EmptyState title="Нет данных за выбранный период" />
      ) : (
        <div className="rounded-xl border border-border bg-surface p-4">
          <p className="text-sm font-medium text-ink">
            {formatDateShort(period.dateFrom)} — {formatDateShort(period.dateTo)}
          </p>
          <div className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
            <Field
              label="Занятий"
              value={`${data.lessons.lessons_scheduled.value} (${data.lessons.lessons_completed.value} проведено)`}
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
