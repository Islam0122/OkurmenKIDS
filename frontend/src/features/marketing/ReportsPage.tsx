import { useState } from 'react'
import { addMonths, addWeeks, parseISO } from 'date-fns'
import { AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, FileCheck2, Info, Send, Target } from 'lucide-react'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { useMarketingReport } from '@/hooks/useMarketing'
import { extractErrorMessage } from '@/lib/apiError'
import type { MarketingReport, ReportPeriod } from '@/types/marketing'
import { cn } from '@/utils/cn'

import { Metric, MetricGrid, ProgressBar, isoDate, monthLabel, rangeLabel, shortDate } from './shared'

/** /marketing/reports — итоги за неделю или месяц по реальным данным
 * контент-плана и задач. Заявок и рекламных кампаний в системе нет — эти
 * показатели не выводятся и не изображаются. */
export function MarketingReportsPage() {
  const [period, setPeriod] = useState<ReportPeriod>('month')
  const [anchor, setAnchor] = useState<string | undefined>(undefined)
  const report = useMarketingReport({ period, date: anchor })

  const move = (delta: number) => {
    if (!report.data) return
    const base = parseISO(report.data.period.date_from)
    setAnchor(isoDate(period === 'week' ? addWeeks(base, delta) : addMonths(base, delta)))
  }

  const r = report.data
  const isCurrent = r ? r.today >= r.period.date_from && r.today <= r.period.date_to : true
  const label = r ? (r.period.kind === 'week' ? rangeLabel(r.period.date_from, r.period.date_to) : monthLabel(r.period.date_from)) : ''

  return (
    <div className="space-y-5">
      <PageHeader title="Отчёты" description="Результаты отдела по контент-плану и задачам" />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <SegmentedControl
          aria-label="Период отчёта"
          value={period}
          onChange={(value) => { setPeriod(value); setAnchor(undefined) }}
          options={[{ value: 'week', label: 'Неделя' }, { value: 'month', label: 'Месяц' }]}
        />
        <div className="flex items-center justify-between gap-1 sm:justify-end">
          <Button variant="ghost" size="sm" className="size-10 px-0" aria-label="Предыдущий период" disabled={!r} onClick={() => move(-1)}>
            <ChevronLeft className="size-5" aria-hidden />
          </Button>
          <span className="min-w-40 text-center text-sm font-semibold text-ink">{label}</span>
          <Button variant="ghost" size="sm" className="size-10 px-0" aria-label="Следующий период" disabled={!r || isCurrent} onClick={() => move(1)}>
            <ChevronRight className="size-5" aria-hidden />
          </Button>
        </div>
      </div>

      {report.isPending ? (
        <LoadingState label="Считаем показатели…" />
      ) : report.isError ? (
        <ErrorState message={extractErrorMessage(report.error)} onRetry={() => void report.refetch()} />
      ) : (
        <div className={cn('space-y-5 transition-opacity', report.isPlaceholderData && 'opacity-60')}>
          <ReportBody r={report.data} />
        </div>
      )}
    </div>
  )
}

function ReportBody({ r }: { r: MarketingReport }) {
  const c = r.content
  const t = r.tasks
  const bucketLabel = (b: MarketingReport['series'][number]) => (b.date_from === b.date_to ? shortDate(b.date_from, true) : rangeLabel(b.date_from, b.date_to, false))

  return (
    <>
      <MetricGrid>
        <Metric
          label="Выполнение плана"
          value={c.plan_completion === null ? '—' : `${c.plan_completion}%`}
          icon={Target}
          hint={c.plan_due ? `Вышло ${c.plan_done} из ${c.plan_due} с наступившей датой` : 'Даты публикаций ещё не наступили'}
        />
        <Metric label="Опубликовано" value={c.published} icon={Send} hint={`Из ${c.planned} в плане периода`} />
        <Metric label="Подготовлено материалов" value={c.prepared} icon={FileCheck2} hint="На согласовании, запланированы или вышли" />
        <Metric label="Выполнено задач" value={t.completed} icon={CheckCircle2} hint={`В срок: ${t.completed_on_time}, с опозданием: ${t.completed_late}`} />
      </MetricGrid>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Динамика" description={r.period.kind === 'week' ? 'По дням недели' : 'По неделям месяца'}>
          <ul className="space-y-3">
            {r.series.map((b) => (
              <li key={b.date_from} className="grid grid-cols-[4.5rem_minmax(0,1fr)] items-center gap-x-3 gap-y-1 sm:grid-cols-[7rem_minmax(0,1fr)_auto]">
                <span className="text-xs text-ink-secondary">{bucketLabel(b)}</span>
                <ProgressBar value={b.published} total={b.planned} label={`Опубликовано ${bucketLabel(b)}`} />
                <span className="col-start-2 text-xs tabular-nums text-ink-secondary sm:col-start-3">
                  {b.published} из {b.planned} · задач: {b.tasks_completed}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-4 text-xs text-ink-muted">Полоса — опубликовано из запланированного на эти даты; «задач» — выполнено в эти дни.</p>
        </Card>

        <Card title="По каналам" description="Опубликовано из запланированного">
          {r.by_channel.length === 0 ? (
            <p className="text-sm text-ink-secondary">В этом периоде публикаций в плане нет.</p>
          ) : (
            <ul className="space-y-3">
              {r.by_channel.map((row) => (
                <li key={row.channel}>
                  <div className="mb-1 flex items-baseline justify-between gap-2 text-sm">
                    <span className="font-medium text-ink">{row.label}</span>
                    <span className="tabular-nums text-ink-secondary">{row.published} из {row.planned}</span>
                  </div>
                  <ProgressBar value={row.published} total={row.planned} label={`${row.label}: опубликовано`} />
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card title="Задачи" description="Состояние на сегодня и за период">
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Fact label="Поставлено за период" value={t.created} />
          <Fact label="Срок в периоде, не выполнены" value={t.open_due_in_period} />
          <Fact label="Выполнено с опозданием" value={t.completed_late} warn={t.completed_late > 0} />
          <Fact label="Просрочено сейчас" value={t.overdue_now} warn={t.overdue_now > 0} icon />
        </dl>
      </Card>

      <Card title="По сотрудникам" padding="none">
        {r.by_person.length === 0 ? (
          <p className="px-4 pb-5 text-sm text-ink-secondary sm:px-5">В этом периоде у сотрудников нет задач и публикаций.</p>
        ) : (
          <>
            <div className="hidden overflow-x-auto md:block">
              <table className="data-table">
                <thead>
                  <tr>
                    <th scope="col">Сотрудник</th>
                    <th scope="col" className="text-right">Публикаций в плане</th>
                    <th scope="col" className="text-right">Опубликовано</th>
                    <th scope="col" className="text-right">Задач выполнено</th>
                    <th scope="col" className="text-right">Открытых задач</th>
                  </tr>
                </thead>
                <tbody>
                  {r.by_person.map((row) => (
                    <tr key={row.id}>
                      <td className="font-medium">{row.full_name}</td>
                      <td className="text-right tabular-nums">{row.content_planned}</td>
                      <td className="text-right tabular-nums">{row.content_published}</td>
                      <td className="text-right tabular-nums">{row.tasks_completed}</td>
                      <td className="text-right tabular-nums">{row.tasks_open}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ul className="divide-y divide-border md:hidden">
              {r.by_person.map((row) => (
                <li key={row.id} className="px-4 py-3">
                  <p className="font-medium text-ink">{row.full_name}</p>
                  <dl className="mt-1 space-y-0.5 text-xs text-ink-secondary">
                    <div className="flex justify-between gap-2"><dt>Опубликовано</dt><dd className="tabular-nums text-ink">{row.content_published} из {row.content_planned}</dd></div>
                    <div className="flex justify-between gap-2"><dt>Задач выполнено</dt><dd className="tabular-nums text-ink">{row.tasks_completed}</dd></div>
                    <div className="flex justify-between gap-2"><dt>Открытых задач</dt><dd className="tabular-nums text-ink">{row.tasks_open}</dd></div>
                  </dl>
                </li>
              ))}
            </ul>
          </>
        )}
      </Card>

      <p className="flex items-start gap-2 text-xs text-ink-muted">
        <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
        Показатели считаются по контент-плану и задачам кабинета. Заявки и рекламные кампании в системе пока не ведутся, поэтому их статистика здесь не выводится.
      </p>
    </>
  )
}

function Fact({ label, value, warn = false, icon = false }: { label: string; value: number; warn?: boolean; icon?: boolean }) {
  return (
    <div className="rounded-xl bg-surface-muted px-3 py-2.5">
      <dt className="text-xs leading-snug text-ink-secondary">{label}</dt>
      <dd className={cn('mt-1 flex items-center gap-1 text-lg font-semibold tabular-nums', warn ? 'text-danger' : 'text-ink')}>
        {icon && warn ? <AlertTriangle className="size-4" aria-hidden /> : null}
        {value}
      </dd>
    </div>
  )
}
