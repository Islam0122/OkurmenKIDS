import { Link } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { StatCard } from '@/components/ui/StatCard'
import { useOpsHeadOfSales, useOpsHr, useOpsMarketing, useOpsSales } from '@/hooks/useOperations'
import type { SalesManagerRow } from '@/types/operations'

import { Counter, LevelBadge, Note, OpsFilters, Progress, QueryView, Section, Table, num, pct, shortDate, useOpsFilters } from './shared'

function CrmNote() {
  return <Note>CRM в LMS не подключена: воронка продаж строится из ежедневных отчётов менеджеров (раздел «Мои отчёты»). План — KPI-цель «Продажи» отдела или менеджера.</Note>
}

function ManagersTable({ rows }: { rows: SalesManagerRow[] }) {
  return (
    <Table empty={!rows.length} headers={['Менеджер', 'Новые заявки', 'Обработано', 'Звонки', 'Встречи', 'Пробные (записаны / пришли)', 'Продажи', 'Конверсия', 'Выручка', 'План / факт', 'Отчёты', 'Задачи']}>
      {rows.map((m) => (
        <tr key={m.id}>
          <td><Link to={`/operations/employees/${m.id}`} className="font-medium hover:text-brand-700">{m.full_name}</Link></td>
          <td className="tabular-nums">{num(m.funnel.leads_new)}</td>
          <td className="tabular-nums">{num(m.funnel.leads_processed)}</td>
          <td className="tabular-nums">{num(m.funnel.calls)}</td>
          <td className="tabular-nums">{num(m.funnel.meetings)}</td>
          <td className="whitespace-nowrap tabular-nums">{num(m.funnel.trials_scheduled)} / {num(m.funnel.trials_attended)}</td>
          <td className="font-semibold tabular-nums">{num(m.funnel.sales)}</td>
          <td>{pct(m.funnel.conversion)}</td>
          <td className="whitespace-nowrap tabular-nums">{'revenue' in m.funnel ? num(m.funnel.revenue, 'сом') : '—'}</td>
          <td className="min-w-32">{m.sales_plan !== null ? <><span className="text-xs">{num(m.sales_fact)} из {num(m.sales_plan)}</span><Progress value={m.plan_achievement} /></> : <span className="text-xs text-ink-muted">план не задан</span>}</td>
          <td className="whitespace-nowrap">{m.reports.expected ? `${m.reports.submitted}/${m.reports.expected}` : `${m.funnel.reports ?? 0} сдано`}</td>
          <td className="whitespace-nowrap text-sm">{m.tasks.open} · <Counter value={m.tasks.overdue} tone="danger" /></td>
        </tr>
      ))}
    </Table>
  )
}

/** /operations/sales — менеджеры по продажам: воронка, конверсия, план и факт. */
export function OperationsSalesPage() {
  const filters = useOpsFilters('this_month')
  const query = useOpsSales(filters.params)
  return (
    <div className="space-y-4">
      <PageHeader title="Менеджеры по продажам" description="Заявки, звонки, встречи, пробные уроки, продажи и конверсия" />
      <OpsFilters filters={filters} />
      <CrmNote />
      <QueryView query={query}>
        {(data) => {
          const d = data.department
          return (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
                <StatCard label="Новые заявки" value={num(d.leads_new)} />
                <StatCard label="Обработано" value={num(d.leads_processed)} />
                <StatCard label="Звонки / встречи" value={`${num(d.calls)} / ${num(d.meetings)}`} />
                <StatCard label="Пробные: пришли" value={num(d.trials_attended)} hint={`явка ${pct(d.trial_attendance)}`} />
                <StatCard label="Продажи" value={num(d.sales)} hint={d.sales_plan !== null ? `план ${num(d.sales_plan)} · ${pct(d.plan_achievement)}` : 'план не задан'} />
                <StatCard label="Конверсия" value={pct(d.conversion)} hint={'revenue' in d ? `выручка ${num(d.revenue, 'сом')}` : undefined} />
              </div>
              <Section title="Менеджеры" padding={false}><ManagersTable rows={data.managers} /></Section>
              {data.daily.length ? (
                <Section title="По дням" padding={false}>
                  <Table headers={['Дата', 'Обработано заявок', 'Звонки', 'Продажи']}>
                    {data.daily.map((row) => <tr key={row.date}><td>{shortDate(row.date)}</td><td>{num(row.leads_processed)}</td><td>{num(row.calls)}</td><td>{num(row.sales)}</td></tr>)}
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

/** /operations/sales-head — РОП: результаты отдела и его работа как руководителя. */
export function OperationsHeadOfSalesPage() {
  const filters = useOpsFilters('this_month')
  const query = useOpsHeadOfSales(filters.params)
  return (
    <div className="space-y-4">
      <PageHeader title="Руководитель отдела продаж" description="План отдела, KPI менеджеров и эффективность РОП как руководителя" />
      <OpsFilters filters={filters} />
      <QueryView query={query}>
        {(data) => (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <StatCard label="Выполнение плана" value={pct(data.department.plan_achievement)} hint={data.department.sales_plan !== null ? `${num(data.department.sales)} из ${num(data.department.sales_plan)}` : 'план не задан'} />
              <StatCard label="Конверсия отдела" value={pct(data.department.conversion)} />
              <StatCard label="Отчёты менеджеров" value={pct(data.team_report_rate)} hint="сданы в срок" />
              <StatCard label="Менеджеров" value={data.managers.length} />
            </div>
            <Section title="РОП / ДОП" padding={false}>
              <Table empty={!data.heads.length} headers={['Руководитель', 'Планёрки', 'Встречи 1:1', 'Проверки CRM', 'Решено ситуаций', 'Проверено отчётов', 'Ждут проверки', 'Задачи команде (поставлено / выполнено)', 'Свои отчёты', 'Свои задачи']}>
                {data.heads.map((h) => (
                  <tr key={h.id}>
                    <td><Link to={`/operations/employees/${h.id}`} className="font-medium hover:text-brand-700">{h.full_name}</Link><span className="block text-xs text-ink-secondary">{h.role_label}</span></td>
                    <td className="tabular-nums">{h.planning_meetings}</td>
                    <td className="tabular-nums">{num(h.one_to_ones)}</td>
                    <td className="tabular-nums">{num(h.crm_checks)}</td>
                    <td className="tabular-nums">{num(h.issues_resolved)}</td>
                    <td className="tabular-nums">{h.team_reports_reviewed}</td>
                    <td><Counter value={h.team_reports_waiting} tone="warning" /></td>
                    <td className="tabular-nums">{h.team_tasks_created} / {h.team_tasks_completed}</td>
                    <td className="whitespace-nowrap">{h.reports.expected ? `${h.reports.submitted}/${h.reports.expected}` : `${h.own_reports} сдано`}</td>
                    <td className="whitespace-nowrap text-sm">{h.tasks.open} · <Counter value={h.tasks.overdue} tone="danger" /></td>
                  </tr>
                ))}
              </Table>
            </Section>
            <Section title="KPI менеджеров" padding={false}><ManagersTable rows={data.managers} /></Section>
            <CrmNote />
          </div>
        )}
      </QueryView>
    </div>
  )
}

/** /operations/marketing — контент-план, кампании, лиды, CPL, задачи отдела. */
export function OperationsMarketingPage() {
  const filters = useOpsFilters('this_month')
  const query = useOpsMarketing(filters.params)
  return (
    <div className="space-y-4">
      <PageHeader title="Маркетинг" description="Контент-план, публикации, рекламные кампании, лиды и задачи отдела" />
      <OpsFilters filters={filters} />
      <QueryView query={query}>
        {(data) => {
          const s = data.summary
          return (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
                <StatCard label="Публикаций в плане" value={s.content_planned} hint={`опубликовано ${s.content_published}`} />
                <StatCard label="Выполнение плана" value={pct(s.plan_completion)} />
                <StatCard label="Кампании" value={s.campaigns} hint={`идут: ${s.campaigns_active}`} />
                <StatCard label="Лиды" value={s.leads} hint={`продаж: ${s.campaign_sales}`} />
                <StatCard label="Конверсия" value={pct(s.conversion)} />
                {data.budget_visible ? <StatCard label="CPL" value={num(s.cost_per_lead, 'сом')} hint={`расход ${num(s.spent, 'сом')} из ${num(s.budget, 'сом')}`} /> : <StatCard label="Задачи" value={s.tasks_open} hint={`просрочено ${s.tasks_overdue}`} />}
              </div>
              {!data.budget_visible ? <Note>Бюджеты и стоимость лида скрыты: доступ к финансовым данным маркетинга не выдан (Настройки).</Note> : null}
              <Section title="Рекламные кампании" padding={false}>
                <Table empty={!data.campaigns.length} headers={['Кампания', 'Канал', 'Ответственный', 'Запуск', 'Статус', ...(data.budget_visible ? ['Бюджет', 'Расход'] : []), 'Лиды', ...(data.budget_visible ? ['CPL'] : []), 'Продажи', 'Конверсия', 'Результат']}>
                  {data.campaigns.map((c) => (
                    <tr key={c.id}>
                      <td className="font-medium">{c.name}</td>
                      <td>{c.channel}</td>
                      <td className="text-sm">{c.responsible ?? '—'}</td>
                      <td className="whitespace-nowrap">{shortDate(c.start_date)}{c.end_date ? ` — ${shortDate(c.end_date)}` : ''}</td>
                      <td><LevelBadge level={c.status === 'active' ? 'ok' : c.status === 'cancelled' ? 'low' : 'no_data'} label={c.status_label} /></td>
                      {data.budget_visible ? <><td className="tabular-nums">{num(c.budget)}</td><td className="tabular-nums">{num(c.spent)}</td></> : null}
                      <td className="tabular-nums">{c.leads}</td>
                      {data.budget_visible ? <td className="tabular-nums">{num(c.cost_per_lead ?? null)}</td> : null}
                      <td className="tabular-nums">{c.sales}</td>
                      <td>{pct(c.conversion)}</td>
                      <td className="max-w-64 truncate text-xs text-ink-secondary">{c.result || '—'}</td>
                    </tr>
                  ))}
                </Table>
              </Section>
              <div className="grid gap-4 lg:grid-cols-3">
                <Section title="Контент-календарь" className="lg:col-span-2" padding={false}>
                  <Table empty={!data.calendar.length} headers={['Дата', 'Тема', 'Канал', 'Ответственный', 'Статус']}>
                    {data.calendar.map((c) => <tr key={c.id}><td className="whitespace-nowrap">{shortDate(c.date)}</td><td>{c.title}</td><td>{c.channel}</td><td className="text-sm">{c.responsible ?? '—'}</td><td><LevelBadge level={c.status === 'published' ? 'ok' : 'no_data'} label={c.status_label} /></td></tr>)}
                  </Table>
                </Section>
                <Section title="Команда и задачи">
                  <p className="mb-3 text-sm">Открыто: <b>{s.tasks_open}</b>, просрочено: <b className="text-danger">{s.tasks_overdue}</b>, выполнено за период: <b>{s.tasks_done}</b></p>
                  <ul className="divide-y divide-border">
                    {data.team.map((m) => <li key={m.id} className="flex items-center justify-between py-2 text-sm"><Link to={`/operations/employees/${m.id}`} className="font-medium hover:text-brand-700">{m.full_name}</Link><span className="text-xs text-ink-secondary">опубл. {m.content_published} · задач {m.tasks.open}</span></li>)}
                  </ul>
                </Section>
              </div>
            </div>
          )
        }}
      </QueryView>
    </div>
  )
}

/** /operations/hr — численность, найм, вакансии, новые сотрудники, работа HR.
 * Без зарплатных данных. */
export function OperationsHrPage() {
  const filters = useOpsFilters('this_month')
  const query = useOpsHr(filters.params)
  return (
    <div className="space-y-4">
      <PageHeader title="HR и сотрудники" description="Сотрудники, найм, вакансии и работа HR" actions={<Link to="/operations/employees" className="text-sm font-medium text-brand-700 hover:underline">Все сотрудники</Link>} />
      <OpsFilters filters={filters} />
      <QueryView query={query}>
        {(data) => (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
              <StatCard label="Активные сотрудники" value={data.active_employees} hint={`неактивных: ${data.inactive_employees}`} />
              <StatCard label="Новые за период" value={data.new_employees_count} />
              <StatCard label="Открытые вакансии" value={data.vacancies.open} hint={`черновики: ${data.vacancies.draft}`} />
              <StatCard label="Отклики" value={data.recruitment.applications} />
              <StatCard label="Собеседования" value={data.recruitment.interviews} />
              <StatCard label="Принято" value={data.recruitment.hired} />
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <Section title="Воронка найма" padding={false}>
                <Table headers={['Этап', 'Кандидатов']}>
                  {data.recruitment.funnel.map((f) => <tr key={f.status}><td>{f.label}</td><td className="tabular-nums">{f.count}</td></tr>)}
                </Table>
              </Section>
              <Section title="Сотрудники по отделам" padding={false}>
                <Table headers={['Отдел', 'Сотрудников']}>
                  {data.by_department.map((d) => <tr key={d.key}><td><Link className="hover:text-brand-700" to={`/operations/departments/${d.key}`}>{d.label}</Link></td><td className="tabular-nums">{d.count}</td></tr>)}
                </Table>
              </Section>
            </div>
            <Section title="Новые сотрудники (адаптация)" padding={false}>
              <Table empty={!data.new_employees.length} headers={['Сотрудник', 'Отдел', 'Должность', 'Начало работы', 'Последний вход']}>
                {data.new_employees.map((e) => <tr key={e.id}><td><Link to={`/operations/employees/${e.id}`} className="font-medium hover:text-brand-700">{e.full_name}</Link></td><td>{e.department_label}</td><td>{e.position}</td><td>{shortDate(e.joined)}</td><td className="text-sm">{e.last_login ? shortDate(e.last_login) : 'ещё не входил'}</td></tr>)}
              </Table>
            </Section>
            <Section title="HR-команда">
              <ul className="divide-y divide-border">
                {data.team.map((m) => <li key={m.id} className="flex items-center justify-between py-2 text-sm"><Link to={`/operations/employees/${m.id}`} className="font-medium hover:text-brand-700">{m.full_name}</Link><span className="text-xs text-ink-secondary">задач открыто {m.tasks.open}, просрочено {m.tasks.overdue}</span></li>)}
              </ul>
            </Section>
            <Note>Документы сотрудников и программа адаптации в LMS пока не ведутся: новые сотрудники показаны по дате начала работы и первому входу. Доступа к зарплатам у HR нет.</Note>
          </div>
        )}
      </QueryView>
    </div>
  )
}
