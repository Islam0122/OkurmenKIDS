import { useState } from 'react'
import { addDays, endOfWeek, format, parseISO } from 'date-fns'
import { ru } from 'date-fns/locale'
import {
  AlertTriangle, ArrowRightLeft, BookOpen, CalendarClock, CalendarPlus, ChevronRight, GraduationCap, History,
  MessageSquarePlus, UserPlus, Users, UserX,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'

import { Card } from '@/components/ui/Card'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { SearchInput } from '@/components/ui/SearchInput'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { useAssistantDashboard, useAssistantGroups, useAssistantSchedule } from '@/hooks/useAssistant'
import { useAuth } from '@/hooks/useAuth'
import type { ActivityRow, AssistantLesson } from '@/types/assistant'
import { pluralize } from '@/utils/format'
import { cn } from '@/utils/cn'

import { useAssistantActions } from '../actions/AssistantActions'

const ATTENTION_TONE = {
  danger: 'text-danger',
  warning: 'text-warning',
  info: 'text-info',
} as const

type Range = 'today' | 'tomorrow' | 'week'
const iso = (date: Date) => format(date, 'yyyy-MM-dd')

function greeting(): string {
  const hour = new Date().getHours()
  if (hour < 12) return 'Доброе утро'
  if (hour < 18) return 'Добрый день'
  return 'Добрый вечер'
}

function Tile({ to, icon: Icon, label, value, hint }: { to: string; icon: LucideIcon; label: string; value: number | string; hint: string }) {
  return (
    <Link to={to} className="card card-interactive flex min-w-0 items-center gap-3 px-4 py-3">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600"><Icon className="size-[18px]" aria-hidden /></span>
      <span className="min-w-0">
        <span className="block text-xs text-ink-secondary">{label}</span>
        <span className="block text-xl leading-tight font-semibold text-ink tabular-nums">{value}</span>
        <span className="block truncate text-2xs text-ink-muted">{hint}</span>
      </span>
    </Link>
  )
}

function LessonRow({ lesson, showDay }: { lesson: AssistantLesson; showDay?: boolean }) {
  const { open } = useAssistantActions()
  return (
    <button type="button" onClick={() => open({ type: 'lesson', lesson })}
      className="grid w-full grid-cols-[3.5rem_minmax(0,1fr)_auto] items-center gap-x-3 px-4 py-2 text-left hover:bg-surface-hover sm:grid-cols-[3.5rem_5.5rem_minmax(0,1fr)_minmax(0,1fr)_4.5rem]">
      <span className="text-sm font-semibold text-ink tabular-nums">
        {lesson.start}
        {showDay ? <span className="block text-2xs font-normal text-ink-muted">{format(parseISO(lesson.date), 'EEEEEE d', { locale: ru })}</span> : null}
      </span>
      <span className="truncate font-medium text-ink">{lesson.group.name}<span className="font-normal text-ink-secondary sm:hidden"> · {lesson.subject?.name ?? '—'}</span></span>
      <span className="hidden truncate text-sm text-ink-secondary sm:block">{lesson.subject?.name ?? '—'}</span>
      <span className="hidden truncate text-sm text-ink-secondary sm:block">{lesson.teacher?.name ?? '—'}</span>
      <span className={cn('text-right text-xs tabular-nums', lesson.status === 'completed' ? 'text-brand-700' : 'text-ink-secondary')}>
        {lesson.status === 'completed' ? 'проведено' : `${lesson.students_count ?? 0} студ.`}
      </span>
    </button>
  )
}

function ScheduleCard() {
  const [range, setRange] = useState<Range>('today')
  const today = new Date()
  const bounds = range === 'today' ? [today, today] : range === 'tomorrow' ? [addDays(today, 1), addDays(today, 1)] : [today, endOfWeek(today, { weekStartsOn: 1 })]
  const { data, isPending } = useAssistantSchedule({ start: iso(bounds[0]), end: iso(bounds[1]) })
  const lessons = data?.lessons ?? []
  return (
    <Card padding="none">
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 sm:px-5">
        <h2 className="section-title">Расписание</h2>
        <SegmentedControl aria-label="Период" value={range} onChange={setRange}
          options={[{ value: 'today', label: 'Сегодня' }, { value: 'tomorrow', label: 'Завтра' }, { value: 'week', label: 'Неделя' }]} />
      </div>
      {isPending ? <LoadingState label="Загружаем…" /> : lessons.length === 0 ? (
        <p className="flex items-center gap-2 px-4 pb-4 text-sm text-ink-secondary sm:px-5"><CalendarClock className="size-4" aria-hidden />Занятий нет.</p>
      ) : (
        <div className="max-h-[22rem] divide-y divide-border overflow-y-auto border-t border-border">
          {lessons.map((lesson) => <LessonRow key={lesson.id} lesson={lesson} showDay={range === 'week'} />)}
        </div>
      )}
      <Link to="/assistant/schedule" className="flex items-center justify-center gap-1 border-t border-border py-2 text-sm font-medium text-brand-700 hover:bg-brand-50">
        Открыть расписание <ChevronRight className="size-4" aria-hidden />
      </Link>
    </Card>
  )
}

function GroupsCard() {
  const [search, setSearch] = useState('')
  const { data, isPending } = useAssistantGroups({ status: 'active', search: search || undefined, page_size: 8 })
  return (
    <Card padding="none">
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 sm:px-5">
        <h2 className="section-title">Все группы</h2>
        <div className="w-full sm:w-56"><SearchInput value={search} onChange={setSearch} placeholder="Найти группу…" /></div>
      </div>
      {isPending ? <LoadingState label="Загружаем…" /> : (
        <div className="divide-y divide-border border-t border-border">
          {(data?.results ?? []).map((group) => (
            <Link key={group.id} to={`/assistant/groups/${group.id}`}
              className="grid grid-cols-[5.5rem_minmax(0,1fr)_auto] items-center gap-x-3 px-4 py-2 text-sm hover:bg-surface-hover sm:grid-cols-[5.5rem_minmax(0,1fr)_5rem_minmax(0,1fr)_minmax(0,1.3fr)]">
              <span className="truncate font-medium text-ink">{group.name}</span>
              <span className="truncate text-ink-secondary">{group.course.name}</span>
              <span className="text-right text-ink tabular-nums sm:text-left">{group.students_count} студ.</span>
              <span className="hidden truncate text-ink-secondary sm:block">{group.teachers.join(', ') || '—'}</span>
              <span className="hidden truncate text-ink-secondary sm:block">{group.schedule || '—'}</span>
            </Link>
          ))}
          {data && data.results.length === 0 ? <p className="px-4 py-3 text-sm text-ink-secondary">Групп не найдено.</p> : null}
        </div>
      )}
      <Link to="/assistant/groups" className="flex items-center justify-center gap-1 border-t border-border py-2 text-sm font-medium text-brand-700 hover:bg-brand-50">
        Все группы{data ? ` (${data.count})` : ''} <ChevronRight className="size-4" aria-hidden />
      </Link>
    </Card>
  )
}

function ActivityList({ rows }: { rows: ActivityRow[] }) {
  if (rows.length === 0) return <p className="text-sm text-ink-secondary">Пока ничего не происходило.</p>
  return (
    <ol className="space-y-2.5">
      {rows.map((row) => {
        const body = (
          <>
            <span className="w-11 shrink-0 text-xs text-ink-muted tabular-nums">{format(parseISO(row.at), 'HH:mm')}</span>
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium text-ink">{row.title}</span>
              <span className="block truncate text-xs text-ink-secondary">{row.detail}{row.by ? ` · ${row.by}` : ''}</span>
            </span>
          </>
        )
        return (
          <li key={row.id}>
            {row.link ? <Link to={row.link} className="-mx-1 flex gap-2 rounded px-1 hover:bg-surface-hover">{body}</Link> : <div className="flex gap-2">{body}</div>}
          </li>
        )
      })}
    </ol>
  )
}

/** The Assistant's operations center: today at a glance, act immediately, details one click away. */
export function AssistantDashboardPage() {
  const { user } = useAuth()
  const { open } = useAssistantActions()
  const navigate = useNavigate()
  const { data, isPending, isError, refetch } = useAssistantDashboard()

  const quick: { icon: LucideIcon; label: string; run: () => void }[] = [
    { icon: Users, label: 'Группа', run: () => open({ type: 'create-group' }) },
    { icon: UserPlus, label: 'Студент', run: () => open({ type: 'create-student' }) },
    { icon: ArrowRightLeft, label: 'Перевод', run: () => open({ type: 'transfer' }) },
    { icon: UserX, label: 'Деактивация', run: () => open({ type: 'deactivate' }) },
    { icon: CalendarPlus, label: 'Расписание', run: () => open({ type: 'schedule' }) },
    { icon: MessageSquarePlus, label: 'Опрос', run: () => navigate('/assistant/surveys?create=1') },
  ]

  return (
    <div>
      <div className="mb-4">
        <h1 className="text-xl font-semibold text-ink sm:text-2xl">{greeting()}{user?.first_name ? `, ${user.first_name}` : ''}</h1>
        <p className="text-sm text-ink-secondary first-letter:uppercase">{format(new Date(), 'EEEE, d MMMM', { locale: ru })}</p>
      </div>
      {isPending ? <LoadingState label="Загружаем данные…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}
      {data ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
            <Tile to="/assistant/groups" icon={Users} label="Группы" value={data.cards.active_groups}
              hint={data.cards.groups_new_this_month ? `+${data.cards.groups_new_this_month} в этом месяце` : 'активных'} />
            <Tile to="/assistant/students" icon={GraduationCap} label="Студенты" value={data.cards.students_total} hint={`${data.cards.active_students} активных`} />
            <Tile to="/assistant/schedule?view=day" icon={BookOpen} label="Сегодня"
              value={`${data.cards.todays_lessons} ${pluralize(data.cards.todays_lessons, 'занятие', 'занятия', 'занятий')}`} hint={`${data.cards.todays_completed} проведено`} />
            <Tile to="/assistant/students?status=active" icon={UserPlus} label="Новые" value={`${data.cards.new_students} студ.`} hint="за 30 дней" />
          </div>

          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
            <div className="min-w-0 space-y-4">
              <ScheduleCard />
              <GroupsCard />
            </div>
            <div className="min-w-0 space-y-4">
              <Card title="Требует внимания">
                {data.attention.length === 0 ? <p className="text-sm text-ink-secondary">Всё в порядке.</p> : (
                  <ul className="-mx-2">
                    {data.attention.map((item) => (
                      <li key={item.key}>
                        <Link to={item.to} className="flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-sm hover:bg-surface-hover">
                          <AlertTriangle className={cn('size-4 shrink-0', ATTENTION_TONE[item.tone])} aria-hidden />
                          <span className="min-w-0 flex-1 truncate text-ink">{item.label}</span>
                          <b className={cn('tabular-nums', ATTENTION_TONE[item.tone])}>{item.count}</b>
                          <ChevronRight className="size-4 shrink-0 text-ink-muted" aria-hidden />
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
              <Card title="Быстрые действия">
                <div className="grid grid-cols-3 gap-2">
                  {quick.map((item) => (
                    <button key={item.label} type="button" onClick={item.run}
                      className="flex flex-col items-center gap-1 rounded-lg border border-border px-1 py-2.5 text-xs font-medium text-ink hover:border-brand-200 hover:bg-brand-50">
                      <item.icon className="size-[18px] text-brand-600" aria-hidden />
                      {item.label}
                    </button>
                  ))}
                </div>
              </Card>
              <Card title="Последние изменения" actions={<History className="size-4 text-ink-muted" aria-hidden />}>
                <ActivityList rows={data.activity} />
              </Card>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
