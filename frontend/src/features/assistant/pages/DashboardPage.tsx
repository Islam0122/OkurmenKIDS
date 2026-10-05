import { AlertTriangle, ArrowRightLeft, Award, BookOpen, CalendarClock, CalendarPlus, ChevronRight, GraduationCap, MessageSquarePlus, UserPlus, Users, UserX } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { StatCard } from '@/components/ui/StatCard'
import { useAssistantDashboard } from '@/hooks/useAssistant'
import { useAuth } from '@/hooks/useAuth'
import { formatDate, pluralize } from '@/utils/format'
import { cn } from '@/utils/cn'

import { useAssistantActions } from '../actions/AssistantActions'

const ATTENTION_TONE = {
  danger: 'border-danger/20 bg-danger-soft text-danger',
  warning: 'border-warning/20 bg-warning-soft text-warning',
  info: 'border-info/20 bg-info-soft text-info',
} as const

function QuickAction({ icon: Icon, label, onClick }: { icon: LucideIcon; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="card card-interactive flex min-h-16 items-center gap-3 px-4 py-3 text-left"
    >
      <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
        <Icon className="size-5" aria-hidden />
      </span>
      <span className="text-sm font-medium text-ink">{label}</span>
    </button>
  )
}

/** The Assistant's day at a glance: four counts, today's lessons, quick actions and what needs attention — no KPI. */
export function AssistantDashboardPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const { open } = useAssistantActions()
  const { data, isPending, isError, refetch } = useAssistantDashboard()

  return (
    <div>
      <PageHeader
        title={`Добрый день${user?.first_name ? `, ${user.first_name}` : ''}`}
        description={data ? `Сегодня ${formatDate(data.date)}` : 'Ежедневные операции академии'}
      />
      {isPending ? <LoadingState label="Загружаем данные…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}
      {data ? (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
            <Link to="/assistant/groups" className="block"><StatCard label="Активные группы" value={data.cards.active_groups} icon={Users} className="h-full" /></Link>
            <Link to="/assistant/students?status=active" className="block"><StatCard label="Активные студенты" value={data.cards.active_students} icon={GraduationCap} className="h-full" /></Link>
            <Link to="/assistant/schedule?view=day" className="block"><StatCard label="Занятий сегодня" value={data.cards.todays_lessons} icon={BookOpen} className="h-full" /></Link>
            <Link to="/assistant/students?status=active" className="block"><StatCard label="Новые студенты" value={data.cards.new_students} hint="за 30 дней" icon={UserPlus} className="h-full" /></Link>
          </div>

          <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
            <Card title="Расписание на сегодня" actions={<Link to="/assistant/schedule?view=day" className="text-sm font-medium text-brand-700 hover:underline">Всё расписание</Link>}>
              {data.today.length === 0 ? (
                <EmptyState icon={CalendarClock} title="Сегодня занятий нет" className="py-6" />
              ) : (
                <ul className="-mx-1 divide-y divide-border">
                  {data.today.map((lesson) => (
                    <li key={lesson.id}>
                      <Link to={`/assistant/groups/${lesson.group.id}`} className="flex items-center gap-4 rounded-lg px-1 py-3 hover:bg-surface-hover">
                        <div className="w-14 shrink-0 text-center">
                          <p className="text-base font-semibold text-ink">{lesson.start}</p>
                          <p className="text-xs text-ink-muted">{lesson.end}</p>
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="truncate font-medium text-ink">{lesson.group.name}<span className="font-normal text-ink-secondary"> · {lesson.subject?.name ?? '—'}</span></p>
                          <p className="truncate text-sm text-ink-secondary">
                            Тренер: {lesson.teacher?.name ?? '—'}{lesson.room ? ` · ${lesson.room.name}` : ''}
                          </p>
                        </div>
                        <div className="hidden shrink-0 text-right sm:block">
                          <p className="text-sm font-medium text-ink">{lesson.students_count ?? 0}</p>
                          <p className="text-xs text-ink-muted">{pluralize(lesson.students_count ?? 0, 'студент', 'студента', 'студентов')}</p>
                        </div>
                        {lesson.status !== 'scheduled' ? <Badge tone={lesson.status === 'completed' ? 'success' : 'info'}>{lesson.status_display}</Badge> : null}
                        <ChevronRight className="size-4 shrink-0 text-ink-muted" aria-hidden />
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <Card title="Требует внимания">
              {data.attention.length === 0 ? (
                <p className="text-sm text-ink-secondary">Всё в порядке — ничего срочного.</p>
              ) : (
                <ul className="space-y-2">
                  {data.attention.map((item) => (
                    <li key={item.key}>
                      <Link to={item.to} className={cn('flex items-center gap-3 rounded-lg border px-3 py-2.5 text-sm hover:opacity-90', ATTENTION_TONE[item.tone])}>
                        <AlertTriangle className="size-4 shrink-0" aria-hidden />
                        <span className="min-w-0 flex-1"><b className="text-base">{item.count}</b> {item.label}</span>
                        <ChevronRight className="size-4 shrink-0" aria-hidden />
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>

          <section>
            <h2 className="section-title mb-3">Быстрые действия</h2>
            <div className="grid grid-cols-1 gap-3 min-[480px]:grid-cols-2 lg:grid-cols-4">
              <QuickAction icon={Users} label="Создать группу" onClick={() => navigate('/assistant/groups/create')} />
              <QuickAction icon={UserPlus} label="Добавить студента" onClick={() => navigate('/assistant/students/create')} />
              <QuickAction icon={ArrowRightLeft} label="Перевести студента" onClick={() => open({ type: 'transfer' })} />
              <QuickAction icon={UserX} label="Деактивировать студента" onClick={() => open({ type: 'deactivate' })} />
              <QuickAction icon={CalendarPlus} label="Расписание" onClick={() => open({ type: 'schedule' })} />
              <QuickAction icon={Award} label="Стипендия" onClick={() => navigate('/assistant/scholarships?create=1')} />
              <QuickAction icon={MessageSquarePlus} label="Опрос" onClick={() => navigate('/assistant/surveys?create=1')} />
            </div>
          </section>
        </div>
      ) : null}
    </div>
  )
}
