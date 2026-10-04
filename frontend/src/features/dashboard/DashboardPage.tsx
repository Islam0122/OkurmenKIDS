import { CalendarDays, ClipboardCheck, NotebookPen, PartyPopper, Percent, Users } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'

import { LESSON_STATUS_LABEL, LESSON_STATUS_TONE } from '@/components/academy/lessonStatus'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { PageHeader } from '@/components/layout/PageHeader'
import { StatCard } from '@/components/ui/StatCard'
import { StatGrid } from '@/components/ui/StatGrid'
import { LiveExamsWidget } from '@/features/exams/LiveExamsWidget'
import { NewsWidget } from '@/features/news/NewsWidget'
import { useAuth } from '@/hooks/useAuth'
import { isTeamLead } from '@/lib/roles'
import { formatTimeRange } from '@/utils/format'

import { useDashboardData } from './useDashboardData'

const GREETING_HOUR_LABEL = (): string => {
  const hour = new Date().getHours()
  if (hour < 5) return 'Доброй ночи'
  if (hour < 12) return 'Доброе утро'
  if (hour < 18) return 'Добрый день'
  return 'Добрый вечер'
}

export function DashboardPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const { data, isPending, isError, refetch } = useDashboardData()

  return (
    <div>
      <PageHeader title={`${GREETING_HOUR_LABEL()}, ${user?.first_name ?? ''}`} description="Вот что у вас сегодня." />

      {isPending ? <LoadingState label="Собираем данные на сегодня…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}

      {data ? (
        <div className="space-y-6">
          <StatGrid>
            <StatCard label="Занятий сегодня" value={data.lessonsToday.length} icon={CalendarDays} />
            <StatCard label="Студентов" value={data.studentsToday} icon={Users} />
            <StatCard
              label="Посещаемость"
              value={data.attendancePercentToday !== null ? `${data.attendancePercentToday}%` : '—'}
              icon={Percent}
              hint={data.attendancePercentToday === null ? 'Ещё не отмечена' : undefined}
            />
            <StatCard
              label="ДЗ на проверку"
              value={data.pendingHomeworkCount}
              icon={NotebookPen}
              tone={data.pendingHomeworkCount > 0 ? 'warning' : 'default'}
            />
          </StatGrid>

          <LiveExamsWidget />

          {isTeamLead(user?.role) ? null : <NewsWidget />}

          <div className="card card-body">
            <h2 className="section-title mb-4">Сегодня</h2>
            {data.lessonsToday.length === 0 ? (
              <EmptyState
                icon={PartyPopper}
                title="На сегодня занятий нет"
                description="Можно перевести дух — или заглянуть в расписание на неделю вперёд."
              />
            ) : (
              <ol className="space-y-3">
                {data.lessonsToday.map((lesson) => (
                  <li key={lesson.id}>
                    <Link
                      to={`/app/lessons/${lesson.id}`}
                      className="flex items-center gap-4 rounded-lg border border-border px-4 py-3 hover:bg-surface-hover"
                    >
                      <span className="w-14 shrink-0 font-mono text-sm text-ink">{lesson.start_time.slice(0, 5)}</span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-medium text-ink">{lesson.subject_name ?? 'Без предмета'}</span>
                        <span className="block text-xs text-ink-secondary">{lesson.group_name}</span>
                      </span>
                      {lesson.status !== 'scheduled' ? (
                        <Badge tone={LESSON_STATUS_TONE[lesson.status]}>{LESSON_STATUS_LABEL[lesson.status]}</Badge>
                      ) : null}
                    </Link>
                  </li>
                ))}
              </ol>
            )}
          </div>

          {(data.tomorrowLessons ?? []).length > 0 ? (
            <div className="card card-body">
              <div className="mb-3 flex items-center justify-between">
                <p className="text-sm font-medium text-ink-secondary">Завтра</p>
                <Link to="/app/lessons?view=tomorrow" className="text-sm text-brand-700 hover:underline">
                  Показать все
                </Link>
              </div>
              <ol className="space-y-3">
                {(data.tomorrowLessons ?? []).map((lesson) => (
                  <li key={lesson.id}>
                    <Link
                      to={`/app/lessons/${lesson.id}`}
                      className="flex items-center gap-4 rounded-lg border border-border px-4 py-3 hover:bg-surface-hover"
                    >
                      <span className="w-14 shrink-0 font-mono text-sm text-ink">{lesson.start_time.slice(0, 5)}</span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-medium text-ink">{lesson.subject_name ?? 'Без предмета'}</span>
                        <span className="block text-xs text-ink-secondary">{lesson.group_name}</span>
                      </span>
                      {lesson.status !== 'scheduled' ? (
                        <Badge tone={LESSON_STATUS_TONE[lesson.status]}>{LESSON_STATUS_LABEL[lesson.status]}</Badge>
                      ) : null}
                    </Link>
                  </li>
                ))}
              </ol>
            </div>
          ) : null}

          {(data.upcomingLessons ?? []).length > 0 ? (
            <div className="card card-body">
              <h2 className="section-title mb-4">Ближайшие занятия</h2>
              <ol className="space-y-3">
                {(data.upcomingLessons ?? []).map((lesson) => (
                  <li key={lesson.id}>
                    <Link
                      to={`/app/lessons/${lesson.id}`}
                      className="flex items-center justify-between gap-4 rounded-lg border border-border px-4 py-3 hover:bg-surface-hover"
                    >
                      <span className="min-w-0">
                        <span className="block text-sm font-medium text-ink">
                          {formatTimeRange(lesson.start_time, lesson.end_time)} · {lesson.subject_name ?? 'Без предмета'}
                        </span>
                        <span className="block text-xs text-ink-secondary">{lesson.group_name}</span>
                      </span>
                      <span className="shrink-0 text-xs text-ink-muted">{lesson.date}</span>
                    </Link>
                  </li>
                ))}
              </ol>
              <div className="mt-4">
                <Button variant="secondary" size="sm" onClick={() => navigate('/app/lessons?view=upcoming')}>
                  Посмотреть все занятия
                </Button>
              </div>
            </div>
          ) : null}

          {data.pendingHomeworkCount > 0 ? (
            <div className="flex flex-wrap items-center justify-between gap-3 card card-body border-warning/20 bg-warning-soft/60">
              <div className="flex min-w-0 items-center gap-3">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-warning-soft text-warning">
                  <ClipboardCheck className="size-5" aria-hidden />
                </span>
                <p className="text-sm text-ink">
                  <strong>Требует внимания.</strong> {data.pendingHomeworkCount} домашних заданий ожидают проверки.
                </p>
              </div>
              <Button variant="secondary" onClick={() => navigate('/app/homework')}>
                Проверить ДЗ
              </Button>
            </div>
          ) : null}

          <div>
            <h2 className="section-title mb-4">Быстрые действия</h2>
            <div className="grid grid-cols-1 gap-3 min-[400px]:grid-cols-2 sm:gap-4 lg:grid-cols-4">
              <Link to="/app/attendance" className="card card-body card-interactive flex items-center gap-3 text-sm font-medium text-ink">
                <ClipboardCheck className="size-5 shrink-0 text-brand-600" aria-hidden />
                <span className="min-w-0">Отметить посещаемость</span>
              </Link>
              <Link to="/app/schedule" className="card card-body card-interactive flex items-center gap-3 text-sm font-medium text-ink">
                <CalendarDays className="size-5 shrink-0 text-brand-600" aria-hidden />
                <span className="min-w-0">Расписание</span>
              </Link>
              <Link to="/app/groups" className="card card-body card-interactive flex items-center gap-3 text-sm font-medium text-ink">
                <Users className="size-5 shrink-0 text-brand-600" aria-hidden />
                <span className="min-w-0">Мои группы</span>
              </Link>
              <Link to="/app/homework" className="card card-body card-interactive flex items-center gap-3 text-sm font-medium text-ink">
                <NotebookPen className="size-5 shrink-0 text-brand-600" aria-hidden />
                <span className="min-w-0">Проверить ДЗ</span>
              </Link>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
