import { useState } from 'react'
import { Briefcase, CalendarCheck2, CalendarClock, CircleCheck, CircleX, Clock4, Handshake, UserCheck, UserPlus, UserSearch, Users } from 'lucide-react'
import { Link } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { DatePicker } from '@/components/ui/DatePicker'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { StatCard } from '@/components/ui/StatCard'
import { StatGrid } from '@/components/ui/StatGrid'
import { useHrDashboard } from '@/hooks/useHr'
import { extractErrorMessage } from '@/lib/apiError'
import { formatDateShort } from '@/utils/format'

import { ActivityList, INTERVIEW_TONE, officeDateTime } from './shared'

/** /hr — главная HR: реальные показатели из базы, ближайшие собеседования и
 * последние кадровые события. */
export function HrDashboardPage() {
  const [period, setPeriod] = useState<{ date_from?: string; date_to?: string }>({})
  const dashboard = useHrDashboard(period)

  if (dashboard.isPending) return <LoadingState label="Загружаем показатели…" />
  if (dashboard.isError) return <ErrorState message={extractErrorMessage(dashboard.error)} onRetry={() => void dashboard.refetch()} />
  const d = dashboard.data

  return (
    <div className="space-y-5">
      <PageHeader title="Главная" description="Кадровая работа: сотрудники, кандидаты и собеседования" />

      <StatGrid columns={4}>
        <StatCard label="Активные сотрудники" value={d.employees_active} icon={Users} hint="В зоне ответственности HR" />
        <StatCard label="Кандидаты в работе" value={d.candidates_in_progress} icon={UserSearch} hint={`Всего в базе: ${d.candidates_total}`} />
        <StatCard label="Собеседования сегодня" value={d.interviews_today} icon={CalendarClock} />
        <StatCard label="Запланировано собеседований" value={d.interviews_scheduled} icon={CalendarCheck2} />
        <StatCard label="Ожидают решения" value={d.awaiting_decision} icon={Clock4} tone={d.awaiting_decision ? 'warning' : 'default'} />
        <StatCard label="Прошли собеседование" value={d.interview_passed} icon={CircleCheck} />
        <StatCard label="Предложение о работе" value={d.offers} icon={Handshake} />
        <StatCard label="Приняты на работу" value={d.hired} icon={UserCheck} />
        <StatCard label="Отказ" value={d.rejected} icon={CircleX} hint={d.withdrawn ? `Кандидат отказался: ${d.withdrawn}` : undefined} />
        <StatCard label="Открытые вакансии" value={d.vacancies_open} icon={Briefcase} />
        <StatCard label="Новые сотрудники" value={d.employees_new} icon={UserPlus} hint={`${formatDateShort(d.period.date_from)} – ${formatDateShort(d.period.date_to)}`} />
      </StatGrid>

      <Card>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <p className="text-sm text-ink-secondary sm:flex-1">Период для «Новые сотрудники» (по умолчанию — с начала месяца)</p>
          <label className="text-sm">
            <span className="mb-1 block field-label">С</span>
            <DatePicker aria-label="Начало периода" value={period.date_from ?? d.period.date_from} onChange={(e) => setPeriod((p) => ({ ...p, date_from: e.target.value || undefined }))} />
          </label>
          <label className="text-sm">
            <span className="mb-1 block field-label">По</span>
            <DatePicker aria-label="Конец периода" value={period.date_to ?? d.period.date_to} onChange={(e) => setPeriod((p) => ({ ...p, date_to: e.target.value || undefined }))} />
          </label>
        </div>
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Ближайшие собеседования" actions={<Link className="text-sm text-brand-700 hover:underline" to="/hr/interviews">Календарь</Link>}>
          {d.upcoming_interviews.length === 0 ? (
            <p className="text-sm text-ink-secondary">Назначенных собеседований нет.</p>
          ) : (
            <ul className="divide-y divide-border">
              {d.upcoming_interviews.map((item) => (
                <li key={item.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
                  <div className="min-w-0">
                    <Link to={`/hr/candidates/${item.candidate.id}`} className="font-medium text-ink hover:text-brand-700">{item.candidate.full_name}</Link>
                    <p className="text-xs text-ink-secondary">{item.position || '—'} · {item.interviewer} · {item.format_label}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm tabular-nums text-ink">{officeDateTime(item.scheduled_at)}</span>
                    <Badge tone={INTERVIEW_TONE[item.status]}>{item.status_label}</Badge>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Последние кадровые события">
          <ActivityList items={d.recent_activity} />
        </Card>
      </div>
    </div>
  )
}
