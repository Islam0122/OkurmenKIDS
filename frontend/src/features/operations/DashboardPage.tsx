import { AlertTriangle, CheckCircle2, ClipboardCheck, Clock, FileCheck2, Gauge, ListTodo, ScanLine, Target, Users } from 'lucide-react'
import { Link } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { StatCard } from '@/components/ui/StatCard'
import { useOpsDashboard } from '@/hooks/useOperations'
import type { Dashboard, ShortTask } from '@/types/operations'

import { Counter, LevelBadge, OpsFilters, PriorityBadge, Progress, QueryView, Section, Table, TaskStatusBadge, dateTime, pct, useOpsFilters } from './shared'

function trend(current: number | null, previous: number | null) {
  if (current === null || previous === null) return undefined
  if (previous === 0) return current === 0 ? { direction: 'stable' as const, changePercent: 0 } : undefined
  const change = Math.round(((current - previous) / previous) * 1000) / 10
  return { direction: change > 0 ? ('up' as const) : change < 0 ? ('down' as const) : ('stable' as const), changePercent: change }
}

function TaskRows({ tasks }: { tasks: ShortTask[] }) {
  if (!tasks.length) return <p className="text-sm text-ink-muted">Задач нет</p>
  return (
    <ul className="divide-y divide-border">
      {tasks.map((t) => (
        <li key={t.id} className="flex flex-col gap-1.5 py-2 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
          <Link to={`/tasks/${t.id}`} className="min-w-0 hover:text-brand-700">
            <span className="block truncate text-sm font-medium">{t.title}</span>
            <span className="block truncate text-xs text-ink-secondary">{t.assignee?.full_name ?? 'Отдел: ' + t.department_label} · {dateTime(t.deadline)}</span>
          </Link>
          <div className="flex shrink-0 items-center gap-1.5">
            <PriorityBadge priority={t.priority} label={t.priority_label} />
            <TaskStatusBadge status={t.status} label={t.status === 'overdue' ? 'Просрочена' : t.status === 'completed' ? 'Выполнена' : 'Открыта'} />
          </div>
        </li>
      ))}
    </ul>
  )
}

function Content({ data }: { data: Dashboard }) {
  const m = data.metrics
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 min-[480px]:grid-cols-2 md:grid-cols-3 xl:grid-cols-5">
        <StatCard label="Всего сотрудников" value={m.total_employees} icon={Users} hint={`Активных: ${m.active_employees}`} />
        <StatCard label="Задач выполнено" value={m.tasks_completed} icon={CheckCircle2} trend={trend(m.tasks_completed, data.previous.tasks_completed)} hint={`к ${data.previous.label}`} />
        <StatCard label="В работе" value={m.tasks_in_progress} icon={ListTodo} />
        <StatCard label="Просрочено" value={m.tasks_overdue} icon={Clock} tone={m.tasks_overdue ? 'danger' : 'default'} />
        <StatCard label="Ждут проверки" value={m.pending_reviews} icon={ClipboardCheck} tone={m.pending_reviews ? 'warning' : 'default'} hint="задачи и отчёты" />
        <StatCard label="Посещаемость сотрудников" value={pct(m.attendance_rate)} icon={ScanLine} trend={trend(m.attendance_rate, data.previous.attendance_rate)} />
        <StatCard label="Отчёты сданы" value={m.reports_expected ? `${m.reports_submitted} / ${m.reports_expected}` : '—'} icon={FileCheck2} hint={m.reports_expected ? undefined : 'обязательные отчёты не заданы'} />
        <StatCard label="Достижение KPI" value={pct(m.kpi.achievement)} icon={Target} hint={m.kpi.targets ? `целей: ${m.kpi.targets}, ниже: ${m.kpi.below_target}` : 'цели KPI не заданы'} />
        <StatCard label="Общая эффективность" value={pct(m.overall_performance)} icon={Gauge} hint="задачи в срок, посещаемость, отчёты" />
        <StatCard label="Требуют внимания" value={data.attention.total} icon={AlertTriangle} tone={data.attention.critical ? 'danger' : 'default'} hint={`высокий приоритет: ${data.attention.critical}`} />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Section title="Эффективность отделов" className="xl:col-span-2" padding={false}
          actions={<Link to="/operations/kpi" className="text-sm font-medium text-brand-700 hover:underline">KPI</Link>}>
          <Table headers={['Отдел', 'Сотрудники', 'Задачи в срок', 'Просрочено', 'Посещаемость', 'Отчёты', 'Проблемы', 'Итог']}>
            {data.departments.map((d) => (
              <tr key={d.key}>
                <td><Link to={`/operations/departments/${d.key}`} className="font-medium hover:text-brand-700">{d.label}</Link></td>
                <td className="tabular-nums">{d.employees}</td>
                <td><Progress value={d.tasks.completion_rate} /></td>
                <td><Counter value={d.tasks.overdue} tone="danger" /></td>
                <td><Progress value={d.attendance_rate} /></td>
                <td className="tabular-nums">{d.reports.expected ? `${d.reports.submitted}/${d.reports.expected}` : '—'}</td>
                <td><Counter value={d.open_issues} tone="warning" /></td>
                <td className="font-semibold tabular-nums">{pct(d.performance)}</td>
              </tr>
            ))}
          </Table>
        </Section>

        <Section title="Требуют внимания" actions={<Link to="/operations/issues" className="text-sm font-medium text-brand-700 hover:underline">Все</Link>}>
          {data.attention.top.length ? (
            <ul className="space-y-2">
              {data.attention.top.map((i) => (
                <li key={i.id}>
                  <Link to={`/operations/issues?open=${i.id}`} className="block rounded-lg border border-border px-3 py-2 hover:border-brand-200">
                    <span className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium">{i.title}</span>
                      <PriorityBadge priority={i.priority} label={i.priority === 'critical' || i.priority === 'high' ? 'Высокий' : 'Средний'} />
                    </span>
                    <span className="block truncate text-xs text-ink-secondary">{i.kind_label} · {i.responsible?.full_name ?? i.department_label}</span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-ink-muted">Открытых проблем нет</p>}
        </Section>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Задачи на сегодня" actions={<Link to="/operations/tasks" className="text-sm font-medium text-brand-700 hover:underline">Все задачи</Link>}>
          <TaskRows tasks={data.today_tasks} />
        </Section>
        <Section title={`Просроченные задачи (${data.overdue_total})`} actions={<Link to="/operations/tasks?status=overdue" className="text-sm font-medium text-brand-700 hover:underline">Открыть</Link>}>
          <TaskRows tasks={data.overdue_tasks} />
        </Section>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Section title="Посещаемость сотрудников" actions={<Link to="/operations/attendance" className="text-sm font-medium text-brand-700 hover:underline">Подробнее</Link>}>
          {data.attendance.today ? (
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <div><dt className="field-label">Пришли сегодня</dt><dd className="text-lg font-semibold tabular-nums">{data.attendance.today.attended_days}</dd></div>
              <div><dt className="field-label">Опоздали</dt><dd className="text-lg font-semibold tabular-nums text-warning">{data.attendance.today.counts.late ?? 0}</dd></div>
              <div><dt className="field-label">Ещё не пришли</dt><dd className="text-lg font-semibold tabular-nums">{data.attendance.today.counts.not_arrived ?? 0}</dd></div>
              <div><dt className="field-label">Без отметки</dt><dd className="text-lg font-semibold tabular-nums text-danger">{data.attendance.today.counts.absent ?? 0}</dd></div>
            </dl>
          ) : null}
          <div className="mt-3"><p className="field-label mb-1">За период</p><Progress value={data.attendance.attendance_rate} /></div>
        </Section>
        <Section title="Отчёты" actions={<Link to="/operations/reports" className="text-sm font-medium text-brand-700 hover:underline">Отчёты</Link>}>
          {data.reports.expected ? (
            <div className="space-y-2 text-sm">
              <Progress value={data.reports.rate} />
              <p>Сдано: <b>{data.reports.submitted}</b>, не сдано: <b className="text-danger">{data.reports.missing}</b>, срок не наступил: {data.reports.pending}</p>
            </div>
          ) : <p className="text-sm text-ink-muted">Обязательные отчёты не настроены. <Link className="text-brand-700 underline" to="/operations/settings">Настройки</Link></p>}
        </Section>
        <Section title="Студенты" actions={<Link to="/operations/students" className="text-sm font-medium text-brand-700 hover:underline">Проблемные</Link>}>
          {data.students ? (
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <div><dt className="field-label">Активные студенты</dt><dd className="text-lg font-semibold tabular-nums">{data.students.active_students}</dd></div>
              <div><dt className="field-label">Активные группы</dt><dd className="text-lg font-semibold tabular-nums">{data.students.active_groups}</dd></div>
              <div><dt className="field-label">Требуют внимания</dt><dd className="text-lg font-semibold tabular-nums text-warning">{data.students.problem_students}</dd></div>
              <div><dt className="field-label">Частые пропуски</dt><dd className="text-lg font-semibold tabular-nums text-danger">{data.students.frequent_absence}</dd></div>
            </dl>
          ) : <p className="text-sm text-ink-muted">Только для академии</p>}
        </Section>
      </div>

      <Section title="Последние события" actions={<Link to="/operations/daily" className="text-sm font-medium text-brand-700 hover:underline">Ежедневный контроль</Link>}>
        {data.activity.length ? (
          <ul className="divide-y divide-border">
            {data.activity.map((e, index) => (
              <li key={index} className="flex items-center justify-between gap-3 py-2 text-sm">
                <Link to={e.link} className="min-w-0 hover:text-brand-700">
                  <span className="block truncate"><LevelBadge level={e.type === 'issue' ? 'open' : e.type === 'report' ? 'submitted' : 'in_progress'} label={e.action} /> <span className="ml-1">{e.title}</span></span>
                  <span className="block truncate text-xs text-ink-secondary">{e.actor?.full_name ?? 'Система'}</span>
                </Link>
                <span className="shrink-0 text-xs text-ink-muted">{dateTime(e.at)}</span>
              </li>
            ))}
          </ul>
        ) : <p className="text-sm text-ink-muted">Событий пока нет</p>}
      </Section>
    </div>
  )
}

/** /operations — главная операционного директора: ключевые показатели,
 * отделы, задачи, посещаемость, отчёты, KPI, проблемы, студенты, события. */
export function OperationsDashboardPage() {
  const filters = useOpsFilters('today')
  const query = useOpsDashboard(filters.params)
  return (
    <div className="space-y-4">
      <PageHeader title="Операционный дашборд" description={query.data ? `${query.data.filters.label}: ${query.data.filters.start === query.data.filters.end ? query.data.filters.start : `${query.data.filters.start} — ${query.data.filters.end}`}` : 'Все отделы, задачи, KPI и посещаемость'} />
      <OpsFilters filters={filters} show={['department', 'role', 'employee']} />
      <QueryView query={query}>{(data) => <Content data={data} />}</QueryView>
    </div>
  )
}
