import { useState } from 'react'
import {
  Briefcase, BriefcaseBusiness, CalendarCheck2, CalendarClock, CircleX, Clock4, Copy, Eye, Handshake, Inbox, UserCheck,
  UserPlus, Users,
} from 'lucide-react'
import { Link } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { DatePicker } from '@/components/ui/DatePicker'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { StatCard } from '@/components/ui/StatCard'
import { StatGrid } from '@/components/ui/StatGrid'
import { useHrDashboard, useHrReminders } from '@/hooks/useHr'
import { extractErrorMessage } from '@/lib/apiError'
import { formatDateShort } from '@/utils/format'

import { ReminderList } from './Reminders'
import { ActivityList, ApplicationStatusBadge, INTERVIEW_TONE, candidatePath, officeDateTime } from './shared'

/** /hr — главная HR: показатели из базы (без демонстрационных данных),
 * напоминания, последние отклики и ближайшие собеседования. */
export function HrDashboardPage() {
  const [period, setPeriod] = useState<{ date_from?: string; date_to?: string }>({})
  const dashboard = useHrDashboard(period)
  const reminders = useHrReminders(false)

  if (dashboard.isPending) return <LoadingState label="Загружаем показатели…" />
  if (dashboard.isError) return <ErrorState message={extractErrorMessage(dashboard.error)} onRetry={() => void dashboard.refetch()} />
  const d = dashboard.data
  const range = `${formatDateShort(d.period.date_from)} – ${formatDateShort(d.period.date_to)}`

  return (
    <div className="space-y-5">
      <PageHeader title="Главная" description="Подбор персонала: вакансии, отклики, собеседования и найм" />

      <StatGrid columns={4}>
        <StatCard label="Открытые вакансии" value={d.vacancies_open} icon={Briefcase}
          hint={[d.vacancies_paused ? `на паузе: ${d.vacancies_paused}` : '', d.vacancies_draft ? `черновиков: ${d.vacancies_draft}` : ''].filter(Boolean).join(' · ') || undefined} />
        <StatCard label="Новые отклики" value={d.applications_new} icon={Inbox} tone={d.applications_new ? 'warning' : 'default'}
          hint={`Сегодня поступило: ${d.applications_today}`} />
        <StatCard label="На первичном рассмотрении" value={d.screening} icon={Eye} hint={d.shortlisted ? `Подходят для собеседования: ${d.shortlisted}` : undefined} />
        <StatCard label="Собеседования сегодня" value={d.interviews_today} icon={CalendarClock} />
        <StatCard label="Предстоящие собеседования" value={d.interviews_upcoming} icon={CalendarCheck2} />
        <StatCard label="Ожидают решения" value={d.awaiting_decision} icon={Clock4} tone={d.awaiting_decision ? 'warning' : 'default'} />
        <StatCard label="Предложения о работе" value={d.offers} icon={Handshake} />
        <StatCard label="Приняты на работу" value={d.hired} icon={UserCheck} hint={`За период: ${d.hired_in_period}`} />
        <StatCard label="Отказы" value={d.rejected} icon={CircleX} hint={d.withdrawn ? `Кандидат отказался: ${d.withdrawn}` : undefined} />
        <StatCard label="Закрытые вакансии" value={d.vacancies_closed} icon={BriefcaseBusiness} />
        <StatCard label="Активные сотрудники" value={d.employees_active} icon={Users} hint={`Новых за период: ${d.employees_new}`} />
        {d.duplicates_to_review ? <StatCard label="Проверить дубли" value={d.duplicates_to_review} icon={Copy} tone="warning" /> : null}
        {d.account_requests_pending ? <StatCard label="Ждут администратора" value={d.account_requests_pending} icon={UserPlus} hint="Запросы учётных записей" /> : null}
      </StatGrid>

      <Card>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <p className="text-sm text-ink-secondary sm:flex-1">Период для «принятые за период» и «новые сотрудники»: {range}</p>
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
        <Card title="Последние отклики" actions={<Link className="text-sm text-brand-700 hover:underline" to="/hr/candidates">Все отклики</Link>}>
          {d.recent_applications.length === 0 ? (
            <p className="text-sm text-ink-secondary">Откликов пока нет. Опубликуйте вакансию — отклики с сайта появятся здесь.</p>
          ) : (
            <ul className="divide-y divide-border">
              {d.recent_applications.map((a) => (
                <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
                  <div className="min-w-0">
                    <Link to={candidatePath(a.candidate.id, a.id)} className="font-medium text-ink hover:text-brand-700">{a.candidate.full_name}</Link>
                    <p className="text-xs text-ink-secondary">{a.position || '—'} · {a.number} · {officeDateTime(a.created_at)}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {a.needs_duplicate_review ? <Badge tone="warning">Дубль?</Badge> : null}
                    <ApplicationStatusBadge status={a.status} label={a.status_label} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Ближайшие собеседования" actions={<Link className="text-sm text-brand-700 hover:underline" to="/hr/interviews">Календарь</Link>}>
          {d.upcoming_interviews.length === 0 ? (
            <p className="text-sm text-ink-secondary">Запланированных собеседований нет.</p>
          ) : (
            <ul className="divide-y divide-border">
              {d.upcoming_interviews.map((item) => (
                <li key={item.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
                  <div className="min-w-0">
                    <Link to={candidatePath(item.candidate.id, item.application)} className="font-medium text-ink hover:text-brand-700">{item.candidate.full_name}</Link>
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
        <Card title="Напоминания">
          {reminders.isPending ? <LoadingState /> : reminders.isError ? (
            <ErrorState message={extractErrorMessage(reminders.error)} onRetry={() => void reminders.refetch()} />
          ) : <ReminderList items={reminders.data.results.slice(0, 10)} />}
        </Card>
        <Card title="Последние кадровые события">
          <ActivityList items={d.recent_activity} />
        </Card>
      </div>
    </div>
  )
}
