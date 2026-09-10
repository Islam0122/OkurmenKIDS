import { ExternalLink, FileText, Youtube } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { useAttendanceRoster } from '@/hooks/useAttendance'
import { useHomeworkList } from '@/hooks/useHomework'
import { useLesson } from '@/hooks/useLessons'
import type { Lesson } from '@/types/academy'
import { formatDate, formatTimeRange } from '@/utils/format'

const STATUS_TONE: Record<Lesson['status'], BadgeTone> = {
  planned: 'muted',
  completed: 'success',
  cancelled: 'danger',
}

export function LessonDetailPage() {
  const { id } = useParams<{ id: string }>()
  const lessonId = Number(id)
  const navigate = useNavigate()

  const { data: lesson, isPending, isError, refetch } = useLesson(lessonId)
  const roster = useAttendanceRoster(lessonId)
  const homeworkList = useHomeworkList({ lesson: lessonId })

  if (isPending) return <LoadingState label="Загружаем занятие…" />
  if (isError || !lesson) return <ErrorState onRetry={() => void refetch()} />

  const present = roster.data?.filter((row) => row.status === 'present').length ?? 0
  const absent = roster.data?.filter((row) => row.status === 'absent').length ?? 0
  const late = roster.data?.filter((row) => row.status === 'late').length ?? 0
  const excused = roster.data?.filter((row) => row.status === 'excused').length ?? 0
  const totalStudents = roster.data?.length ?? 0

  const homework = homeworkList.data?.results[0]

  return (
    <div>
      <PageHeader
        title={formatTimeRange(lesson.start_time, lesson.end_time)}
        description={`${formatDate(lesson.date)} · ${lesson.subject_name ?? 'Без предмета'}${lesson.topic ? ` — ${lesson.topic}` : ''}`}
        actions={<Badge tone={STATUS_TONE[lesson.status]}>{lesson.status_display}</Badge>}
      />

      {lesson.status === 'cancelled' && lesson.cancellation_reason ? (
        <div className="mb-6 rounded-lg bg-danger-soft px-4 py-3 text-sm text-danger">
          Занятие отменено. Причина: {lesson.cancellation_reason}
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <div className="rounded-xl border border-border bg-surface p-5">
            <p className="mb-3 text-sm font-medium text-ink-secondary">О занятии</p>
            <dl className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <dt className="text-ink-secondary">Группа</dt>
                <dd className="mt-0.5">
                  <Link to={`/app/groups/${lesson.group}`} className="font-medium text-brand-700 hover:underline">
                    {lesson.group_name}
                  </Link>
                </dd>
              </div>
              <div>
                <dt className="text-ink-secondary">Аудитория</dt>
                <dd className="mt-0.5 font-medium text-ink">{lesson.room_name ?? '—'}</dd>
              </div>
            </dl>
            {lesson.description ? <p className="mt-4 text-sm text-ink">{lesson.description}</p> : null}
          </div>

          {(lesson.youtube_url || lesson.presentation_urls.length > 0) ? (
            <div className="rounded-xl border border-border bg-surface p-5">
              <p className="mb-3 text-sm font-medium text-ink-secondary">Материалы</p>
              <ul className="space-y-2">
                {lesson.youtube_url ? (
                  <li>
                    <a
                      href={lesson.youtube_url}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center gap-2 text-sm text-brand-700 hover:underline"
                    >
                      <Youtube className="size-4" aria-hidden />
                      YouTube
                      <ExternalLink className="size-3" aria-hidden />
                    </a>
                  </li>
                ) : null}
                {lesson.presentation_urls.map((url, index) => (
                  <li key={url}>
                    <a href={url} target="_blank" rel="noreferrer" className="flex items-center gap-2 text-sm text-brand-700 hover:underline">
                      <FileText className="size-4" aria-hidden />
                      Презентация {lesson.presentation_urls.length > 1 ? index + 1 : ''}
                      <ExternalLink className="size-3" aria-hidden />
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="rounded-xl border border-border bg-surface p-5">
            <div className="mb-3 flex items-center justify-between">
              <p className="text-sm font-medium text-ink-secondary">Посещаемость</p>
              <span className="text-sm text-ink-secondary">{totalStudents} студентов</span>
            </div>
            {roster.isPending ? (
              <LoadingState label="Загружаем…" />
            ) : (
              <div className="grid grid-cols-4 gap-2 text-center">
                <StatBlock label="Present" value={present} tone="success" />
                <StatBlock label="Absent" value={absent} tone="danger" />
                <StatBlock label="Late" value={late} tone="warning" />
                <StatBlock label="Excused" value={excused} tone="muted" />
              </div>
            )}
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-xl border border-border bg-surface p-5">
            <p className="mb-3 text-sm font-medium text-ink-secondary">Действия</p>
            <div className="space-y-2">
              <Button className="w-full" onClick={() => navigate(`/app/attendance?lesson=${lesson.id}`)}>
                Отметить посещаемость
              </Button>
              {homework ? (
                <Button variant="secondary" className="w-full" onClick={() => navigate(`/app/homework/${homework.id}`)}>
                  Открыть ДЗ
                </Button>
              ) : null}
            </div>
          </div>

          {homework ? (
            <div className="rounded-xl border border-border bg-surface p-5">
              <p className="mb-2 text-sm font-medium text-ink-secondary">Домашнее задание</p>
              <p className="font-medium text-ink">{homework.title}</p>
              {homework.deadline ? <p className="mt-1 text-sm text-ink-secondary">Срок: {formatDate(homework.deadline)}</p> : null}
              <p className="mt-2 text-sm text-ink-secondary">{homework.results_count} результатов</p>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function StatBlock({ label, value, tone }: { label: string; value: number; tone: BadgeTone }) {
  const TONE_TEXT: Record<BadgeTone, string> = {
    success: 'text-brand-700',
    danger: 'text-danger',
    warning: 'text-warning',
    muted: 'text-ink-muted',
    brand: 'text-brand-700',
  }
  return (
    <div className="rounded-lg bg-surface-muted p-3">
      <p className={`text-xl font-semibold ${TONE_TEXT[tone]}`}>{value}</p>
      <p className="text-xs text-ink-secondary">{label}</p>
    </div>
  )
}
