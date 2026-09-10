import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import { DataTable } from '@/components/ui/DataTable'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAttendanceList } from '@/hooks/useAttendance'
import { useGroup } from '@/hooks/useGroups'
import { useHomeworkList } from '@/hooks/useHomework'
import { useKPIGroups } from '@/hooks/useKPI'
import { useLessons } from '@/hooks/useLessons'
import { useStudents } from '@/hooks/useStudents'
import type { Group } from '@/types/academy'
import { ATTENDANCE_STATUS_LABELS } from '@/types/attendance'
import { DAY_LABELS } from '@/types/common'
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
  { key: 'lessons', label: 'Занятия' },
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
      {tab === 'lessons' ? <LessonsTab groupId={groupId} /> : null}
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

function LessonsTab({ groupId }: { groupId: number }) {
  const { data, isPending, isError, refetch } = useLessons({ group: groupId, ordering: '-date' })

  if (isPending) return <LoadingState label="Загружаем занятия…" />
  if (isError) return <ErrorState onRetry={() => void refetch()} />
  if (data.results.length === 0) return <EmptyState title="Занятий пока нет" description="Сгенерируйте занятия по курсу в Django Admin." />

  return (
    <ul className="space-y-2">
      {data.results.map((lesson) => (
        <li key={lesson.id}>
          <Link to={`/app/lessons/${lesson.id}`} className="flex items-center justify-between rounded-lg border border-border bg-surface px-4 py-3 hover:bg-surface-hover">
            <span className="text-sm text-ink">
              {formatDateShort(lesson.date)} · {formatTimeRange(lesson.start_time, lesson.end_time)}
            </span>
            <span className="text-sm text-ink-secondary">{lesson.subject_name ?? 'Без предмета'}</span>
          </Link>
        </li>
      ))}
    </ul>
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

function KpiTab({ groupId }: { groupId: number }) {
  const { data, isPending, isError, refetch } = useKPIGroups({ group: groupId, ordering: '-date_to' })

  if (isPending) return <LoadingState label="Загружаем KPI…" />
  if (isError) return <ErrorState onRetry={() => void refetch()} />
  if (data.results.length === 0) return <EmptyState title="KPI для этой группы ещё не рассчитаны" description="Расчёт запускает администратор." />

  return (
    <div className="space-y-3">
      {data.results.map((kpi) => (
        <div key={kpi.id} className="rounded-xl border border-border bg-surface p-4">
          <p className="text-sm font-medium text-ink">
            {formatDateShort(kpi.date_from)} — {formatDateShort(kpi.date_to)}
          </p>
          <div className="mt-3 grid grid-cols-3 gap-3 text-sm">
            <Field label="Посещаемость" value={`${kpi.attendance_percent}%`} />
            <Field label="Выполнение ДЗ" value={`${kpi.homework_completion_percent}%`} />
            <Field label="Средний балл" value={`${kpi.average_score}/10`} />
          </div>
        </div>
      ))}
    </div>
  )
}
