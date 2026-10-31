import { useState } from 'react'
import { AlertTriangle, CalendarCheck2, CalendarClock, CheckCircle2, ChevronLeft, ChevronRight, ClipboardList, Lightbulb, PenLine, Plus, Send } from 'lucide-react'
import { addMonths, endOfMonth, parseISO, startOfMonth } from 'date-fns'
import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { useAuth } from '@/hooks/useAuth'
import { useMarketingDashboard, useMarketingMeta } from '@/hooks/useMarketing'
import { extractErrorMessage } from '@/lib/apiError'
import type { ContentItem, MarketingTask } from '@/types/marketing'
import { pluralize } from '@/utils/format'

import { ContentDialog, TaskDialog, type ContentDraft } from './Dialogs'
import { ContentRow, TaskRow } from './Rows'
import { Metric, MetricGrid, isoDate, longDate, monthLabel } from './shared'
import { WorkdayCard } from './Workday'

function greeting(hour: number): string {
  if (hour < 5) return 'Доброй ночи'
  if (hour < 12) return 'Доброе утро'
  if (hour < 18) return 'Добрый день'
  return 'Добрый вечер'
}

/** /marketing — обзор: приветствие, рабочий день, сводка задач и контент-плана
 * за месяц, ближайшие задачи и публикации. Только данные из базы. */
export function MarketingOverviewPage() {
  const { user } = useAuth()
  useMarketingMeta()
  // Месяц сводки: смещение от текущего (0 — этот месяц).
  const [shift, setShift] = useState(0)
  const [month, setMonth] = useState<{ date_from?: string; date_to?: string }>({})
  const dashboard = useMarketingDashboard(month)
  const [task, setTask] = useState<MarketingTask | null | undefined>(undefined)
  const [content, setContent] = useState<ContentDraft | null>(null)

  if (dashboard.isPending) return <LoadingState label="Загружаем обзор…" />
  if (dashboard.isError) return <ErrorState message={extractErrorMessage(dashboard.error)} onRetry={() => void dashboard.refetch()} />
  const d = dashboard.data
  const t = d.tasks
  const c = d.content

  const moveMonth = (delta: number) => {
    const next = shift + delta
    const anchor = addMonths(startOfMonth(parseISO(d.today)), next)
    setShift(next)
    setMonth(next === 0 ? {} : { date_from: isoDate(anchor), date_to: isoDate(endOfMonth(anchor)) })
  }

  return (
    <div className="space-y-5">
      <section className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <p className="text-sm text-ink-secondary">{longDate(d.today)}</p>
          <h1 className="mt-0.5 text-xl font-semibold text-ink sm:text-2xl">{greeting(new Date().getHours())}, {user?.first_name}!</h1>
          <p className="mt-1 text-sm text-ink-secondary">
            {t.mine_open
              ? `У вас ${t.mine_open} ${pluralize(t.mine_open, 'открытая задача', 'открытые задачи', 'открытых задач')}`
              : 'Открытых задач на вас нет'}
            {t.overdue ? `, просрочено в отделе: ${t.overdue}` : ''}.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:flex">
          <Button variant="secondary" className="max-sm:h-11" leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setTask(null)}>Задача</Button>
          <Button className="max-sm:h-11" leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setContent({})}>Публикация</Button>
          <Link to="/marketing/campaigns" className="col-span-2 flex h-11 items-center justify-center rounded-lg border border-brand-200 text-sm font-medium text-brand-700 hover:bg-brand-50 sm:h-10 sm:px-4">Кампании</Link>
        </div>
      </section>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <section aria-label="Сводка" className="min-w-0 space-y-3">
          <div className="flex items-center justify-between gap-2">
            <h2 className="section-title">Сводка</h2>
            <div className="flex items-center">
              <Button variant="ghost" size="sm" className="size-9 px-0" aria-label="Предыдущий месяц" onClick={() => moveMonth(-1)}>
                <ChevronLeft className="size-4" aria-hidden />
              </Button>
              <span className="min-w-28 text-center text-sm font-medium text-ink">{monthLabel(d.period.date_from)}</span>
              <Button variant="ghost" size="sm" className="size-9 px-0" aria-label="Следующий месяц" disabled={shift >= 0} onClick={() => moveMonth(1)}>
                <ChevronRight className="size-4" aria-hidden />
              </Button>
            </div>
          </div>
          <MetricGrid>
            <Metric label="Открытые задачи" value={t.open} icon={ClipboardList} hint={`В работе: ${t.in_progress}`} />
            <Metric label="Просрочено" value={t.overdue} icon={AlertTriangle} tone={t.overdue ? 'danger' : 'default'} hint="Сейчас, по всему отделу" />
            <Metric label="Срок сегодня" value={t.due_today} icon={CalendarClock} tone={t.due_today ? 'warning' : 'default'} hint="Открытые задачи" />
            <Metric label="Выполнено задач" value={t.done_in_period} icon={CheckCircle2} hint="За выбранный месяц" />
            <Metric label="Опубликовано" value={c.published_in_period} icon={Send} hint={`Из ${c.planned_in_period} в плане месяца`} />
            <Metric label="Идеи" value={c.ideas} icon={Lightbulb} tone="info" hint="Ждут проработки" />
            <Metric label="В подготовке" value={c.in_work} icon={PenLine} tone="warning" hint="Подготовка и согласование" />
            <Metric label="Запланировано" value={c.scheduled} icon={CalendarCheck2} hint="Готовы к выходу" />
          </MetricGrid>
        </section>
        <div className="order-first min-w-0 xl:order-none xl:pt-10">
          <WorkdayCard />
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card
          padding="none"
          title="Ближайшие задачи"
          actions={<Link className="text-sm font-medium text-brand-700 hover:underline" to="/marketing/tasks">Все задачи</Link>}
        >
          {d.upcoming_tasks.length === 0 ? (
            <p className="px-4 pb-5 text-sm text-ink-secondary sm:px-5">Открытых задач нет.</p>
          ) : (
            <ul className="divide-y divide-border pb-1">
              {d.upcoming_tasks.map((item) => <TaskRow key={item.id} task={item} onOpen={setTask} />)}
            </ul>
          )}
        </Card>
        <Card
          padding="none"
          title="Ближайшие публикации"
          actions={<Link className="text-sm font-medium text-brand-700 hover:underline" to="/marketing/content">Контент-план</Link>}
        >
          {d.upcoming_content.length === 0 ? (
            <p className="px-4 pb-5 text-sm text-ink-secondary sm:px-5">Запланированных публикаций нет.</p>
          ) : (
            <ul className="divide-y divide-border pb-1">
              {d.upcoming_content.map((item) => <ContentRow key={item.id} item={item} onOpen={(i: ContentItem) => setContent({ item: i })} />)}
            </ul>
          )}
        </Card>
      </div>

      <TaskDialog task={task} onClose={() => setTask(undefined)} />
      <ContentDialog draft={content} onClose={() => setContent(null)} />
    </div>
  )
}
