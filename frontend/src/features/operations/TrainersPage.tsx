import { AlertTriangle, BookOpenCheck, GraduationCap, Target } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { BackLink } from '@/components/ui/BackLink'
import { Badge } from '@/components/ui/Badge'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { StatCard } from '@/components/ui/StatCard'
import { useOpsMeta, useOpsTrainer, useOpsTrainers } from '@/hooks/useOperations'
import type { TrainerRow } from '@/types/operations'

import { Counter, KpiValue, LevelBadge, OpsFilters, Progress, QueryView, Section, Table, dateTime, pct, shortDate, useOpsFilters } from './shared'

const JOURNAL_STATUSES = [
  { value: 'problem', label: 'Проблема' },
  { value: 'attention', label: 'Внимание' },
  { value: 'ok', label: 'OK' },
  { value: 'no_data', label: 'Нет данных' },
  { value: 'upcoming', label: 'Предстоящие' },
]
const KPI_LEVELS = [
  { value: 'good', label: 'KPI: хороший' },
  { value: 'attention', label: 'KPI: внимание' },
  { value: 'low', label: 'KPI: низкий' },
  { value: 'no_data', label: 'KPI: нет данных' },
]

function TrainerCell({ row }: { row: TrainerRow }) {
  return (
    <Link to={`/operations/trainers/${row.id}`} className="flex min-w-48 items-center gap-2.5 hover:text-brand-700">
      {row.photo ? <img src={row.photo} alt="" className="size-9 shrink-0 rounded-full object-cover" /> : (
        <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-brand-100 text-xs font-semibold text-brand-700">{row.name.slice(0, 2).toUpperCase()}</span>
      )}
      <span className="min-w-0">
        <span className="block truncate font-medium">{row.name}</span>
        <span className="block truncate text-xs text-ink-secondary">{row.subjects.join(', ') || row.position}{row.is_active ? '' : ' · неактивен'}</span>
      </span>
    </Link>
  )
}

/** /operations/trainers — все тренеры одной таблицей: журнал, посещаемость,
 * ДЗ, KPI, отчёты, задачи и предупреждения (только по наступившим срокам). */
export function OperationsTrainersPage() {
  const filters = useOpsFilters('this_week')
  const meta = useOpsMeta()
  const query = useOpsTrainers(filters.params)
  const { raw, set } = filters
  return (
    <div className="space-y-4">
      <PageHeader title="Тренеры" description="Журнал занятий, посещаемость, домашние задания, KPI и отчёты каждого тренера" />
      <OpsFilters filters={filters}>
        <div className="col-span-2 md:w-60"><SearchInput value={raw.get('q') ?? ''} onChange={(v) => set({ q: v })} placeholder="Поиск тренера" /></div>
        <div className="md:w-44"><Select aria-label="Предмет" placeholder="Все предметы" value={raw.get('subject') ?? ''} options={(meta.data?.subjects ?? []).map((s) => ({ value: String(s.id), label: s.name }))} onChange={(e) => set({ subject: e.target.value })} /></div>
        <div className="md:w-44"><Select aria-label="Группа" placeholder="Все группы" value={raw.get('group') ?? ''} options={(meta.data?.groups ?? []).map((g) => ({ value: String(g.id), label: g.name }))} onChange={(e) => set({ group: e.target.value })} /></div>
        <div className="md:w-44"><Select aria-label="KPI" placeholder="Любой KPI" value={raw.get('kpi_level') ?? ''} options={KPI_LEVELS} onChange={(e) => set({ kpi_level: e.target.value })} /></div>
        <div className="md:w-48"><Select aria-label="Журнал" placeholder="Журнал: любой" value={raw.get('journal_status') ?? ''} options={JOURNAL_STATUSES} onChange={(e) => set({ journal_status: e.target.value })} /></div>
      </OpsFilters>
      <QueryView query={query}>
        {(data) => (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <StatCard label="Тренеров" value={data.summary.trainers} icon={GraduationCap} />
              <StatCard label="С предупреждениями" value={data.summary.with_warnings} icon={AlertTriangle} tone={data.summary.with_warnings ? 'warning' : 'default'} />
              <StatCard label="Средний KPI" value={pct(data.summary.average_kpi)} icon={Target} />
              <StatCard label="Журнал не заполнен" value={data.summary.warnings.journal_not_filled ?? 0} icon={BookOpenCheck} tone={data.summary.warnings.journal_not_filled ? 'danger' : 'default'} />
            </div>
            <div className="flex flex-wrap gap-2 print:hidden">
              {Object.entries(data.warning_labels).map(([key, label]) => (
                <button key={key} type="button" onClick={() => set({ warning: raw.get('warning') === key ? undefined : key })}
                  className={raw.get('warning') === key ? 'rounded-full bg-danger px-3 py-1 text-xs font-medium text-white' : 'rounded-full border border-border bg-surface px-3 py-1 text-xs font-medium text-ink-secondary hover:border-brand-200'}>
                  {label}: {data.summary.warnings[key] ?? 0}
                </button>
              ))}
            </div>
            <Section title="Мониторинг тренеров" padding={false}>
              <Table empty={!data.trainers.length} headers={['Тренер', 'Группы / студенты', 'Журнал', 'Не закрыто', 'Посещ. не отмечена', 'ДЗ на проверке', 'KPI', 'Отчёты', 'Задачи', 'Предупреждения']}>
                {data.trainers.map((row) => (
                  <tr key={row.id}>
                    <td><TrainerCell row={row} /></td>
                    <td className="whitespace-nowrap text-sm">{row.groups.length} / {row.students}</td>
                    <td className="min-w-32"><Progress value={row.journal.completion} /><span className="text-xs text-ink-muted">обновлено: {dateTime(row.journal.last_activity_at)}</span></td>
                    <td><Counter value={row.journal.not_closed} tone="danger" /></td>
                    <td><Counter value={row.journal.attendance_missing} tone="danger" /></td>
                    <td><Counter value={row.journal.homework_awaiting_review} tone="warning" /></td>
                    <td className="whitespace-nowrap"><KpiValue value={row.kpi} level={row.kpi_level} />{row.kpi_target !== null ? <span className="block text-xs text-ink-muted">цель {pct(row.kpi_target)}</span> : null}</td>
                    <td className="whitespace-nowrap text-sm">{row.reports.expected ? `${row.reports.submitted}/${row.reports.expected}` : '—'}</td>
                    <td className="whitespace-nowrap text-sm">{row.tasks.open} откр. · <Counter value={row.tasks.overdue} tone="danger" /> просроч.</td>
                    <td className="min-w-44"><div className="flex flex-wrap gap-1">{row.warnings.length ? row.warnings.map((w) => <Badge key={w.key} tone={w.key === 'homework_not_checked' ? 'warning' : 'danger'}>{w.label}</Badge>) : <Badge tone="success">Всё в порядке</Badge>}</div></td>
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

/** /operations/trainers/:id — профиль тренера: группы и журнал по каждой,
 * KPI, проблемные студенты, отчёты, задачи. */
export function OperationsTrainerDetailPage() {
  const { id } = useParams()
  const filters = useOpsFilters('this_month')
  const query = useOpsTrainer(Number(id), filters.params)
  return (
    <div className="space-y-4">
      <BackLink to="/operations/trainers">Все тренеры</BackLink>
      <QueryView query={query}>
        {(data) => {
          const t = data.trainer
          return (
            <div className="space-y-4">
              <PageHeader title={t.name} description={`${t.position} · ${t.subjects.join(', ') || 'предметы не указаны'}`}
                badge={<LevelBadge level={t.is_active ? 'ok' : 'no_data'} label={t.is_active ? 'Работает' : 'Неактивен'} />}
                actions={<Link to={`/operations/employees/${t.user_id}`} className="text-sm font-medium text-brand-700 hover:underline">Профиль сотрудника</Link>} />
              <OpsFilters filters={filters} />
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
                <StatCard label="KPI" value={pct(t.kpi)} hint={t.kpi_target !== null ? `цель ${pct(t.kpi_target)}` : 'цель не задана'} />
                <StatCard label="Журнал заполнен" value={pct(t.journal.completion)} hint={`${t.journal.lessons_closed} из ${t.journal.lessons_due} занятий`} />
                <StatCard label="Посещаемость студентов" value={pct(t.attendance_rate)} />
                <StatCard label="ДЗ проверено" value={t.journal.homework_checked} hint={`ждут проверки: ${t.journal.homework_awaiting_review}`} tone={t.journal.homework_awaiting_review ? 'warning' : 'default'} />
                <StatCard label="Задачи" value={t.tasks.open} hint={`просрочено: ${t.tasks.overdue}`} tone={t.tasks.overdue ? 'danger' : 'default'} />
              </div>
              {t.warnings.length ? <div className="flex flex-wrap gap-1.5">{t.warnings.map((w) => <Badge key={w.key} tone="danger">{w.label}</Badge>)}</div> : null}
              <Section title="Журнал по группам (Контроль занятий)" padding={false}>
                <Table empty={!data.control.rows.length} headers={['Группа', 'Предметы', 'Занятия закрыты', 'Посещаемость', 'ДЗ', 'Оценки', 'Статус', 'Что осталось']}>
                  {data.control.rows.map((r) => (
                    <tr key={r.key}>
                      <td className="font-medium">{r.group.name}</td>
                      <td className="text-sm">{r.subjects.map((s) => s.name).join(', ')}</td>
                      <td className="whitespace-nowrap text-sm">{r.lessons.completed}/{r.lessons.total}{r.lessons.upcoming ? <span className="text-ink-muted"> (+{r.lessons.upcoming} впереди)</span> : null}</td>
                      <td><Progress value={r.attendance.percent} /></td>
                      <td><Progress value={r.homework.percent} /></td>
                      <td><Progress value={r.grades.percent} /></td>
                      <td><LevelBadge level={r.status} label={r.status_label} /></td>
                      <td className="text-xs text-ink-secondary">{r.issues.join('; ') || '—'}</td>
                    </tr>
                  ))}
                </Table>
              </Section>
              <div className="grid gap-4 lg:grid-cols-2">
                <Section title="Проблемные студенты" padding={false}>
                  <Table empty={!data.problem_students.length} headers={['Студент', 'Группа', 'Посещаемость', 'Пропуски подряд', 'Статус']}>
                    {data.problem_students.map((s) => (
                      <tr key={s.student_id}>
                        <td className="font-medium">{s.name}</td>
                        <td className="text-sm">{s.group?.name ?? '—'}</td>
                        <td>{pct(s.attendance)}</td>
                        <td><Counter value={s.consecutive_absences} tone="danger" /></td>
                        <td><LevelBadge level={s.status} label={s.status_label} /></td>
                      </tr>
                    ))}
                  </Table>
                </Section>
                <Section title="Отчёты" padding={false}>
                  <Table empty={!data.reports.length && !data.monthly_reports.length} headers={['Отчёт', 'Период', 'Срок', 'Статус']}>
                    {data.reports.map((r) => (
                      <tr key={`${r.kind}-${r.period_start}`}>
                        <td>{r.kind === 'daily' ? 'Ежедневный' : r.kind === 'weekly' ? 'Еженедельный' : 'Ежемесячный'}</td>
                        <td>{shortDate(r.period_start)}</td>
                        <td className="text-sm">{dateTime(r.due)}</td>
                        <td><LevelBadge level={r.status} label={r.status === 'submitted' ? 'Сдан' : r.status === 'missing' ? 'Не сдан' : 'Срок не наступил'} /></td>
                      </tr>
                    ))}
                    {data.monthly_reports.map((r) => (
                      <tr key={`m-${r.id}`}>
                        <td>Месячный отчёт тренера</td>
                        <td>{String(r.month).padStart(2, '0')}.{r.year}</td>
                        <td className="text-sm">{dateTime(r.updated_at)}</td>
                        <td><LevelBadge level={r.comment ? 'submitted' : 'draft'} label={r.comment ? 'С комментарием' : 'Без комментария'} /></td>
                      </tr>
                    ))}
                  </Table>
                </Section>
              </div>
              <Section title="Задачи тренера" actions={<Link to={`/operations/tasks?assignee=${t.user_id}`} className="text-sm font-medium text-brand-700 hover:underline">Все задачи</Link>}>
                <p className="text-sm text-ink-secondary">Открыто: {t.tasks.open}, на проверке: {t.tasks.review}, выполнено: {t.tasks.completed}, просрочено: <b className="text-danger">{t.tasks.overdue}</b>.</p>
              </Section>
            </div>
          )
        }}
      </QueryView>
    </div>
  )
}
