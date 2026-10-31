import { Link } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { Select } from '@/components/ui/Select'
import { StatCard } from '@/components/ui/StatCard'
import { useOpsMeta, useOpsProblemStudents, useOpsTeamLeads } from '@/hooks/useOperations'

import { Counter, LevelBadge, Note, OpsFilters, Progress, QueryView, Section, Table, num, pct, shortDate, useOpsFilters } from './shared'

function reports(r: { expected: number; submitted: number }) {
  return r.expected ? `${r.submitted}/${r.expected}` : '—'
}

/** /operations/team-leads — работа тимлидов (журнал, отчёты, проверки,
 * задачи, состояние академии) и ассистентов (пропуски, родители, таблицы). */
export function OperationsTeamLeadsPage() {
  const filters = useOpsFilters('this_week')
  const query = useOpsTeamLeads(filters.params)
  return (
    <div className="space-y-4">
      <PageHeader title="Тимлиды и ассистенты" description="Контроль работы руководителей тренеров и ассистентов академии"
        actions={<Link to="/operations/students" className="text-sm font-medium text-brand-700 hover:underline">Проблемные студенты</Link>} />
      <OpsFilters filters={filters} />
      <QueryView query={query}>
        {(data) => (
          <div className="space-y-4">
            <Section title="Тимлиды" padding={false}>
              <Table empty={!data.team_leads.length} headers={['Тимлид', 'Команда', 'Рабочий журнал', 'Отчёты (ежедн./нед./мес.)', 'Обязательные отчёты', 'Проверено отчётов', 'Задачи', 'Академия: требуют внимания', 'Посещаемость отмечена', 'ДЗ проверены']}>
                {data.team_leads.map((l) => (
                  <tr key={l.id}>
                    <td><Link to={`/operations/employees/${l.id}`} className="font-medium hover:text-brand-700">{l.name}</Link></td>
                    <td className="tabular-nums">{l.team_size} тренеров</td>
                    <td className="tabular-nums">{l.worklog_entries} записей</td>
                    <td className="whitespace-nowrap tabular-nums">{l.reports.daily ?? 0} / {l.reports.weekly ?? 0} / {l.reports.monthly ?? 0}</td>
                    <td>{reports(l.report_obligations)}</td>
                    <td className="tabular-nums">{l.reports_reviewed}</td>
                    <td className="whitespace-nowrap text-sm">{l.tasks.open} откр. · <Counter value={l.tasks.overdue} tone="danger" /> просроч.</td>
                    <td><Counter value={l.academy_control.attention} tone="warning" /> групп, <Counter value={l.academy_control.problem_lessons} tone="danger" /> занятий</td>
                    <td><Progress value={l.academy_control.attendance_completion} /></td>
                    <td><Progress value={l.academy_control.homework_completion} /></td>
                  </tr>
                ))}
              </Table>
            </Section>
            <Note>В LMS тимлид руководит всеми тренерами академии: отдельной привязки «тимлид → свои тренеры» нет, поэтому команда — все активные тренеры, а качество — сводка Контроля занятий по академии.</Note>
            <Section title="Ассистенты" padding={false}>
              <Table empty={!data.assistants.length} headers={['Ассистент', 'Связь с родителями', 'Отработано пропусков', 'Обновлено таблиц', 'Ежедневные отчёты', 'Задачи']}>
                {data.assistants.map((a) => (
                  <tr key={a.id}>
                    <td><Link to={`/operations/employees/${a.id}`} className="font-medium hover:text-brand-700">{a.name}</Link></td>
                    <td className="tabular-nums">{num(a.parents_contacted)}</td>
                    <td className="tabular-nums">{num(a.absences_followed_up)}</td>
                    <td className="tabular-nums">{num(a.tables_updated)}</td>
                    <td>{reports(a.report_obligations)}</td>
                    <td className="whitespace-nowrap text-sm">{a.tasks.open} откр. · <Counter value={a.tasks.overdue} tone="danger" /> просроч.</td>
                  </tr>
                ))}
              </Table>
            </Section>
            <Note>Показатели ассистента — из его сданных ежедневных отчётов; пропуски и домашние задания студентов — из «Контроля активности».</Note>
          </div>
        )}
      </QueryView>
    </div>
  )
}

/** /operations/students — проблемные студенты (пороги «Контроля активности»
 * ассистента) и проблемные группы. */
export function OperationsStudentsPage() {
  const filters = useOpsFilters('this_month')
  const meta = useOpsMeta()
  const query = useOpsProblemStudents(filters.params)
  return (
    <div className="space-y-4">
      <PageHeader title="Проблемные студенты" description="Частые пропуски, низкая активность и группы, требующие внимания" />
      <OpsFilters filters={filters} periods={['this_week', 'this_month', 'last_month', 'custom']}>
        <div className="md:w-52"><Select aria-label="Группа" placeholder="Все группы" value={filters.raw.get('group') ?? ''} options={(meta.data?.groups ?? []).map((g) => ({ value: String(g.id), label: g.name }))} onChange={(e) => filters.set({ group: e.target.value })} /></div>
      </OpsFilters>
      <QueryView query={query}>
        {(data) => (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <StatCard label="Активные студенты" value={data.summary.active_students} />
              <StatCard label="Требуют внимания" value={data.summary.problem_students} tone="warning" />
              <StatCard label="В зоне риска" value={data.summary.risk} tone="danger" />
              <StatCard label="Частые пропуски" value={data.summary.frequent_absence} tone="danger" />
            </div>
            {data.groups.length ? (
              <Section title="Проблемные группы" padding={false}>
                <Table headers={['Группа', 'Причина', 'Посещаемость', 'KPI']}>
                  {data.groups.map((g) => <tr key={g.id}><td className="font-medium">{g.name}</td><td>{g.reason}</td><td>{pct(g.attendance_rate)}</td><td>{pct(g.kpi)}</td></tr>)}
                </Table>
              </Section>
            ) : null}
            <Section title="Студенты" padding={false}>
              <Table empty={!data.students.length} headers={['Студент', 'Группа', 'Тренер', 'Посещаемость', 'Пропусков', 'Подряд', 'ДЗ', 'Последняя активность', 'Статус', 'Причины']}>
                {data.students.map((s) => (
                  <tr key={s.student_id}>
                    <td className="font-medium">{s.name}</td>
                    <td className="text-sm">{s.group?.name ?? '—'}</td>
                    <td className="text-sm">{s.last_teacher || '—'}</td>
                    <td>{pct(s.attendance)}</td>
                    <td className="tabular-nums">{s.absent}</td>
                    <td><Counter value={s.consecutive_absences} tone="danger" /></td>
                    <td>{pct(s.homework)}</td>
                    <td className="text-sm">{shortDate(s.last_activity)}</td>
                    <td><LevelBadge level={s.status} label={s.status_label} /></td>
                    <td className="text-xs text-ink-secondary">{s.category_labels.join(', ') || '—'}</td>
                  </tr>
                ))}
              </Table>
            </Section>
          </div>
        )}
      </QueryView>
    </div>
  )
}
