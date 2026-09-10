import { CalendarDays, ClipboardCheck, NotebookPen, PartyPopper, Percent, Users } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'

import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { PageHeader } from '@/components/layout/PageHeader'
import { StatCard } from '@/components/ui/StatCard'
import { useAuth } from '@/hooks/useAuth'
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
      <PageHeader title={`${GREETING_HOUR_LABEL()}, ${user?.first_name ?? ''} 👋`} description="Вот что у вас сегодня." />

      {isPending ? <LoadingState label="Собираем данные на сегодня…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}

      {data ? (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
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
          </div>

          {data.nextLesson ? (
            <div className="rounded-xl border border-border bg-surface p-5">
              <p className="text-sm font-medium text-ink-secondary">Ближайшее занятие</p>
              <div className="mt-2 flex flex-wrap items-end justify-between gap-4">
                <div>
                  <p className="text-2xl font-semibold text-ink">{formatTimeRange(data.nextLesson.start_time, data.nextLesson.end_time)}</p>
                  <p className="mt-1 text-sm text-ink-secondary">{data.nextLesson.subject_name ?? 'Без предмета'}</p>
                  <p className="mt-3 text-sm text-ink">
                    Группа: <span className="font-medium">{data.nextLesson.group_name}</span>
                  </p>
                  {data.nextLesson.room_name ? (
                    <p className="text-sm text-ink-secondary">Аудитория: {data.nextLesson.room_name}</p>
                  ) : null}
                </div>
                <Button onClick={() => navigate(`/app/lessons/${data.nextLesson?.id}`)}>Открыть занятие</Button>
              </div>
            </div>
          ) : null}

          <div className="rounded-xl border border-border bg-surface p-5">
            <p className="mb-3 text-sm font-medium text-ink-secondary">Сегодня</p>
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
                      <span className="flex-1">
                        <span className="block text-sm font-medium text-ink">{lesson.subject_name ?? 'Без предмета'}</span>
                        <span className="block text-xs text-ink-secondary">{lesson.group_name}</span>
                      </span>
                      {lesson.status === 'cancelled' ? <Badge tone="danger">Отменено</Badge> : null}
                    </Link>
                  </li>
                ))}
              </ol>
            )}
          </div>

          {data.pendingHomeworkCount > 0 ? (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-warning-soft bg-warning-soft/60 p-5">
              <div className="flex items-center gap-3">
                <span className="flex size-10 items-center justify-center rounded-lg bg-warning-soft text-warning">
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
            <p className="mb-3 text-sm font-medium text-ink-secondary">Быстрые действия</p>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Link to="/app/attendance" className="rounded-xl border border-border bg-surface p-4 text-sm font-medium text-ink hover:bg-surface-hover">
                Отметить посещаемость
              </Link>
              <Link to="/app/schedule" className="rounded-xl border border-border bg-surface p-4 text-sm font-medium text-ink hover:bg-surface-hover">
                Расписание
              </Link>
              <Link to="/app/groups" className="rounded-xl border border-border bg-surface p-4 text-sm font-medium text-ink hover:bg-surface-hover">
                Мои группы
              </Link>
              <Link to="/app/homework" className="rounded-xl border border-border bg-surface p-4 text-sm font-medium text-ink hover:bg-surface-hover">
                Проверить ДЗ
              </Link>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
