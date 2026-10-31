import { Link, useParams } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { BackLink } from '@/components/ui/BackLink'
import { SearchInput } from '@/components/ui/SearchInput'
import { StatCard } from '@/components/ui/StatCard'
import { useOpsDepartment, useOpsEmployee, useOpsEmployees } from '@/hooks/useOperations'
import type { EmployeeRow, KpiValue } from '@/types/operations'

import { Counter, LevelBadge, OpsFilters, Progress, QueryView, Section, Table, TaskStatusBadge, dateTime, num, pct, shortDate, time, useOpsFilters } from './shared'

function EmployeesTable({ rows }: { rows: EmployeeRow[] }) {
  return (
    <Table empty={!rows.length} headers={['Сотрудник', 'Отдел', 'Должность', 'Задачи: открыто', 'Просрочено', 'Выполнено', 'Отчёты', 'Посещаемость', 'Опоздания, мин']}>
      {rows.map((e) => (
        <tr key={e.id}>
          <td><Link to={`/operations/employees/${e.id}`} className="font-medium hover:text-brand-700">{e.full_name}</Link>{e.is_active ? null : <span className="ml-1 text-xs text-ink-muted">неактивен</span>}</td>
          <td className="text-sm">{e.department_label}</td>
          <td className="text-sm">{e.position}</td>
          <td className="tabular-nums">{e.tasks.open}</td>
          <td><Counter value={e.tasks.overdue} tone="danger" /></td>
          <td className="tabular-nums">{e.tasks.completed}</td>
          <td className="whitespace-nowrap">{e.reports.expected ? `${e.reports.submitted}/${e.reports.expected}` : '—'}</td>
          <td>{e.attendance ? <Progress value={e.attendance.attendance_rate} /> : '—'}</td>
          <td className="tabular-nums">{e.attendance ? e.attendance.late_minutes : '—'}</td>
        </tr>
      ))}
    </Table>
  )
}

/** /operations/employees — все сотрудники с задачами, отчётами и посещаемостью. */
export function OperationsEmployeesPage() {
  const filters = useOpsFilters('this_month')
  const query = useOpsEmployees(filters.params)
  return (
    <div className="space-y-4">
      <PageHeader title="Сотрудники" description="Индивидуальная работа каждого сотрудника за период" />
      <OpsFilters filters={filters} show={['department', 'role']}>
        <div className="col-span-2 md:w-60"><SearchInput value={filters.raw.get('q') ?? ''} onChange={(v) => filters.set({ q: v })} placeholder="Поиск сотрудника" /></div>
      </OpsFilters>
      <QueryView query={query}>
        {(data) => <Section title={`Сотрудники (${data.total})`} padding={false}><EmployeesTable rows={data.employees} /></Section>}
      </QueryView>
    </div>
  )
}

function formatKpi(m: KpiValue, value: number | null) {
  if (value === null) return '—'
  return m.unit === 'percent' ? pct(value) : num(value, m.unit === 'money' ? 'сом' : m.unit === 'minutes' ? 'мин' : '')
}

/** /operations/employees/:id — профиль сотрудника: задачи, отчёты,
 * посещаемость, KPI, история показателей, проблемы, подчинённые. */
export function OperationsEmployeePage() {
  const { id } = useParams()
  const filters = useOpsFilters('this_month')
  const query = useOpsEmployee(Number(id), filters.params)
  return (
    <div className="space-y-4">
      <BackLink to="/operations/employees">Все сотрудники</BackLink>
      <QueryView query={query}>
        {(data) => {
          const e = data.employee
          return (
            <div className="space-y-4">
              <PageHeader title={e.full_name} description={`${e.position} · ${e.department_label} · работает с ${shortDate(e.joined)}`}
                badge={<LevelBadge level={e.is_active ? 'ok' : 'no_data'} label={e.is_active ? 'Активен' : 'Неактивен'} />}
                actions={e.teacher_id ? <Link to={`/operations/trainers/${e.teacher_id}`} className="text-sm font-medium text-brand-700 hover:underline">Контроль тренера</Link> : null} />
              <OpsFilters filters={filters} />
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
                <StatCard label="Открытые задачи" value={data.tasks.open} />
                <StatCard label="Просрочено" value={data.tasks.overdue} tone={data.tasks.overdue ? 'danger' : 'default'} />
                <StatCard label="Выполнено за период" value={data.tasks.completed_in_period} />
                <StatCard label="Отчёты" value={data.reports.summary.expected ? `${data.reports.summary.submitted}/${data.reports.summary.expected}` : '—'} hint={data.reports.summary.expected ? undefined : 'не обязательны'} />
                <StatCard label="Посещаемость" value={pct(data.attendance?.summary.attendance_rate)} hint={data.attendance ? `опоздания ${data.attendance.summary.late_minutes} мин` : 'не отмечает приход'} />
              </div>
              <div className="grid gap-4 lg:grid-cols-2">
                <Section title="KPI" padding={false}>
                  <Table empty={!data.kpi.length} headers={['Показатель', 'Факт', 'Цель', 'Достижение']}>
                    {data.kpi.map((m) => <tr key={m.key}><td>{m.label}</td><td className="font-semibold">{formatKpi(m, m.actual)}</td><td>{m.target !== null ? formatKpi(m, m.target) : '—'}</td><td>{m.achievement !== null ? <Progress value={m.achievement} /> : '—'}</td></tr>)}
                  </Table>
                </Section>
                <Section title="История выполнения задач" padding={false}>
                  <Table headers={['Месяц', 'Выполнено', 'В срок']}>
                    {data.history.map((h) => <tr key={h.month}><td>{h.month}</td><td>{h.tasks_completed}</td><td><Progress value={h.task_completion_rate} /></td></tr>)}
                  </Table>
                </Section>
              </div>
              <Section title="Задачи" padding={false} actions={<Link to={`/operations/tasks?assignee=${e.id}`} className="text-sm font-medium text-brand-700 hover:underline">Все задачи</Link>}>
                <Table empty={!data.tasks.open_items.length} headers={['Задача', 'Дедлайн', 'Статус']}>
                  {data.tasks.open_items.map((t) => <tr key={t.id}><td><Link to={`/tasks/${t.id}`} className="hover:text-brand-700">{t.title}</Link></td><td className="text-sm">{dateTime(t.deadline)}</td><td><TaskStatusBadge status={t.status} label={t.status_label} /></td></tr>)}
                </Table>
              </Section>
              <div className="grid gap-4 lg:grid-cols-2">
                <Section title="Отчёты" padding={false}>
                  <Table empty={!data.reports.recent.length && !data.reports.obligations.length} headers={['Отчёт', 'Период', 'Статус']}>
                    {data.reports.obligations.filter((o) => o.status === 'missing').map((o) => <tr key={`m-${o.kind}-${o.period_start}`}><td>{o.kind === 'daily' ? 'Ежедневный' : o.kind === 'weekly' ? 'Еженедельный' : 'Ежемесячный'}</td><td>{shortDate(o.period_start)}</td><td><LevelBadge level="missing" label="Не сдан" /></td></tr>)}
                    {data.reports.recent.map((r) => <tr key={r.id}><td>{r.kind_label}</td><td>{shortDate(r.period_start)}</td><td><LevelBadge level={r.status} label={r.status_label} /></td></tr>)}
                  </Table>
                </Section>
                <Section title="Посещаемость" padding={false}>
                  <Table empty={!data.attendance?.days.length} headers={['Дата', 'Приход', 'Уход', 'Статус']}>
                    {(data.attendance?.days ?? []).slice().reverse().map((d) => <tr key={d.date}><td>{shortDate(d.date)}</td><td>{time(d.check_in)}</td><td>{time(d.check_out)}</td><td><LevelBadge level={d.status} label={d.status_label} /></td></tr>)}
                  </Table>
                </Section>
              </div>
              {data.subordinates.length ? (
                <Section title="Сотрудники в подчинении" padding={false}>
                  <Table headers={['Сотрудник', 'Должность']}>
                    {data.subordinates.map((s) => <tr key={s.id}><td><Link to={`/operations/employees/${s.id}`} className="hover:text-brand-700">{s.full_name}</Link></td><td>{s.position}</td></tr>)}
                  </Table>
                </Section>
              ) : null}
              {data.issues.length ? (
                <Section title="Открытые проблемы" padding={false}>
                  <Table headers={['Проблема', 'Статус']}>
                    {data.issues.map((i) => <tr key={i.id}><td><Link to={`/operations/issues?open=${i.id}`} className="hover:text-brand-700">{i.title}</Link></td><td><LevelBadge level={i.status} label={i.status} /></td></tr>)}
                  </Table>
                </Section>
              ) : null}
            </div>
          )
        }}
      </QueryView>
    </div>
  )
}

/** /operations/departments/:key — отдел: сводка, сотрудники и KPI. */
export function OperationsDepartmentPage() {
  const { key = '' } = useParams()
  const filters = useOpsFilters('this_month')
  const query = useOpsDepartment(key, filters.params)
  return (
    <div className="space-y-4">
      <BackLink to="/operations">Дашборд</BackLink>
      <QueryView query={query}>
        {(data) => (
          <div className="space-y-4">
            <PageHeader title={data.department.label} description={`Должности: ${data.roles.map((r) => r.label).join(', ')}`} />
            <OpsFilters filters={filters} />
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
              <StatCard label="Сотрудники" value={data.department.employees} />
              <StatCard label="Задачи в срок" value={pct(data.department.tasks.completion_rate)} />
              <StatCard label="Просрочено" value={data.department.tasks.overdue} tone={data.department.tasks.overdue ? 'danger' : 'default'} />
              <StatCard label="Посещаемость" value={pct(data.department.attendance_rate)} />
              <StatCard label="Открытых проблем" value={data.department.open_issues} />
            </div>
            <Section title="Сотрудники" padding={false}><EmployeesTable rows={data.employees} /></Section>
            <Section title="KPI отдела" padding={false}>
              <Table empty={!data.kpi.metrics.length} headers={['Показатель', 'Факт', 'Цель', 'Достижение', 'Прошлый период']}>
                {data.kpi.metrics.map((m) => <tr key={m.key}><td>{m.label}</td><td className="font-semibold">{formatKpi(m, m.actual)}</td><td>{m.target !== null ? formatKpi(m, m.target) : '—'}</td><td>{m.achievement !== null ? <Progress value={m.achievement} /> : '—'}</td><td>{formatKpi(m, m.previous ?? null)}</td></tr>)}
              </Table>
            </Section>
          </div>
        )}
      </QueryView>
    </div>
  )
}
