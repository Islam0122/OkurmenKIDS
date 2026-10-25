import { useQuery } from '@tanstack/react-query'
import { AlarmClock, Plus, TriangleAlert, Wallet } from 'lucide-react'
import { Link, Navigate, useNavigate } from 'react-router-dom'

import { financeApi } from '@/api/finance'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { LoadingState } from '@/components/ui/LoadingState'

import { PeriodReportCard } from './PeriodReportCard'
import { useFinancePeriod } from './period'
import { FINANCE_KEY, Loadable, Stat, StageBadge, som, useFinanceMe } from './ui'

/** Главная бухгалтера: что требует действия сегодня, деньги выбранного
 * периода (по умолчанию — текущий месяц; можно открыть прошлый), ссылки на очереди. */
export function FinanceDashboardPage() {
  const me = useFinanceMe()
  const period = useFinancePeriod()
  const navigate = useNavigate()
  const money = me.data?.can_view_money ?? false
  const counts = useQuery({ queryKey: [...FINANCE_KEY, 'counts'], queryFn: financeApi.counts, enabled: money })
  const dashboard = useQuery({ queryKey: [...FINANCE_KEY, 'dashboard'], queryFn: financeApi.dashboard, enabled: money })
  const overdue = useQuery({ queryKey: [...FINANCE_KEY, 'queue', 'overdue', 'top'], queryFn: () => financeApi.queue('overdue', { page_size: 5 }), enabled: money })
  const analytics = useQuery({
    queryKey: [...FINANCE_KEY, 'analytics', period.date_from, period.date_to],
    queryFn: () => financeApi.analytics({ date_from: period.date_from, date_to: period.date_to }), enabled: money,
  })

  if (me.isLoading) return <LoadingState />
  if (me.data && !money) return <Navigate to="/finance/students" replace />

  return (
    <div>
      <PageHeader title="Финансы" description={`Кому пора платить и у кого просрочка — сейчас; деньги и начисления — за период «${period.label}».`}
        actions={me.data?.can_record_payments ? <Button leftIcon={<Plus className="size-4" />} onClick={() => navigate('/finance/payments/new')}>Добавить платёж</Button> : undefined} />
      <div className="grid gap-3 sm:grid-cols-3">
        <QueueTile to="/finance/to-pay" icon={<Wallet className="size-5" />} label="К оплате" count={counts.data?.to_pay} tone="text-brand-700" />
        <QueueTile to="/finance/soon" icon={<AlarmClock className="size-5" />} label="Скоро оплата" count={counts.data?.soon} tone="text-warning" />
        <QueueTile to="/finance/overdue" icon={<TriangleAlert className="size-5" />} label="Просроченные" count={counts.data?.overdue} tone="text-danger" />
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <Stat label={`Ожидалось: ${period.label}`} value={som(analytics.data?.expected.amount)} hint={analytics.data ? `срок оплаты в периоде; не оплачено ${som(analytics.data.expected.unpaid)}` : undefined} />
        <Stat label="Долг сейчас" value={som(dashboard.data?.total_debt)} hint={dashboard.data ? `просрочено ${som(dashboard.data.overdue_amount)}` : undefined} tone="danger" />
        <Link to="/finance/prepayments" className="block rounded-xl transition-shadow hover:shadow-md focus-visible:outline-2 focus-visible:outline-brand-500"
          aria-label="Остаток предоплаты за обучение — открыть детализацию по ученикам">
          <Stat label="Остаток предоплаты за обучение" value={som(dashboard.data?.prepayment_total)}
            hint="Деньги, полученные от родителей за обучение заранее и ещё не зачтённые в оплату учебных месяцев" />
        </Link>
      </div>
      {money ? <div className="mt-4"><PeriodReportCard compact /></div> : null}
      <Card className="mt-4" title="Дольше всех просрочено" actions={<Link to="/finance/overdue" className="text-sm text-brand-700 hover:underline">Все просроченные</Link>}>
        <Loadable query={overdue} empty={(d) => d.count === 0} emptyTitle="Просрочек нет">
          {(data) => (
            <ul className="divide-y divide-border">
              {data.results.map((r) => (
                <li key={r.profile}>
                  <Link to={`/finance/students/${r.profile}`} className="flex items-center justify-between gap-3 py-2.5 hover:bg-surface-hover">
                    <span><span className="font-medium">{r.student_name}</span>
                      <span className="block text-xs text-ink-secondary">{r.group_name} · {r.parent_phone}</span></span>
                    <span className="flex items-center gap-3"><span className="font-semibold tabular-nums text-danger">{som(r.overdue_amount)}</span><StageBadge stage={r.stage} /></span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Loadable>
      </Card>
    </div>
  )
}

function QueueTile({ to, icon, label, count, tone }: { to: string; icon: React.ReactNode; label: string; count?: number; tone: string }) {
  return (
    <Link to={to} className="card flex items-center justify-between p-4 transition-colors hover:bg-surface-hover">
      <span className="flex items-center gap-2 font-medium text-ink"><span className={tone}>{icon}</span>{label}</span>
      <span className={`text-2xl font-semibold tabular-nums ${tone}`}>{count ?? '—'}</span>
    </Link>
  )
}
