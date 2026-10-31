import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { Link } from 'react-router-dom'

import { TrendChart } from '@/components/charts/TrendChart'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { SearchInput } from '@/components/ui/SearchInput'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { StatCard } from '@/components/ui/StatCard'
import { useToast } from '@/components/ui/Toast'
import { useDeleteTarget, useOpsAttendance, useOpsDaily, useOpsKpi, useOpsKpiHistory, useOpsMeta, useOpsTargets, useSaveTarget } from '@/hooks/useOperations'
import { extractErrorMessage } from '@/lib/apiError'
import type { KpiTargetInput, KpiValue, MetricInfo } from '@/types/operations'

import { Counter, LevelBadge, Note, OpsFilters, PriorityBadge, Progress, QueryView, Section, Table, dateTime, num, pct, shortDate, time, useOpsFilters } from './shared'

type AttendanceView = 'daily' | 'departments' | 'employees'

/** /operations/attendance — посещаемость сотрудников из существующего учёта
 * прихода и ухода по QR (второй системы отметки нет). */
export function OperationsAttendancePage() {
  const filters = useOpsFilters('today')
  const query = useOpsAttendance(filters.params)
  const [view, setView] = useState<AttendanceView>('daily')
  const { raw, set } = filters
  return (
    <div className="space-y-4">
      <PageHeader title="Посещаемость сотрудников" description="Приход и уход по QR-коду офиса с учётом графика, выходных и льготного времени" />
      <OpsFilters filters={filters} show={['department', 'role']}>
        <div className="col-span-2 md:w-56"><SearchInput value={raw.get('q') ?? ''} onChange={(v) => set({ q: v })} placeholder="Поиск сотрудника" /></div>
        <div className="md:w-48"><Select aria-label="Статус" placeholder="Все статусы" value={raw.get('status') ?? ''} options={query.data?.statuses ?? []} onChange={(e) => set({ status: e.target.value })} /></div>
      </OpsFilters>
      <QueryView query={query}>
        {(data) => {
          const c = data.summary.counts
          return (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
                <StatCard label="Посещаемость" value={pct(data.summary.attendance_rate)} />
                <StatCard label="Вовремя" value={c.present ?? 0} hint={`пунктуальность ${pct(data.summary.punctuality_rate)}`} />
                <StatCard label="Опоздания" value={c.late ?? 0} tone={c.late ? 'warning' : 'default'} hint={`${data.summary.late_minutes} мин`} />
                <StatCard label="Отсутствие" value={c.absent ?? 0} tone={c.absent ? 'danger' : 'default'} />
                <StatCard label="Нет ухода" value={c.not_checked_out ?? 0} />
                <StatCard label="Отработано" value={`${num(data.summary.worked_hours)} ч`} />
              </div>
              <SegmentedControl aria-label="Вид" value={view} onChange={setView} options={[{ value: 'daily', label: 'По дням' }, { value: 'departments', label: 'По отделам' }, { value: 'employees', label: 'По сотрудникам' }]} />
              {view === 'daily' ? (
                <Section title="Отметки" padding={false}>
                  <Table empty={!data.rows.length} headers={['Сотрудник', 'Отдел', 'Должность', 'Дата', 'Приход', 'Уход', 'Часы', 'Опоздание', 'Статус', 'Геолокация']}>
                    {data.rows.map((r) => (
                      <tr key={`${r.user.id}-${r.date}`}>
                        <td><Link to={`/operations/employees/${r.user.id}`} className="font-medium hover:text-brand-700">{r.user.full_name}</Link></td>
                        <td className="text-sm">{r.user.department}</td>
                        <td className="text-sm">{r.user.role_label}</td>
                        <td className="whitespace-nowrap">{shortDate(r.date)}</td>
                        <td className="tabular-nums">{time(r.check_in)}</td>
                        <td className="tabular-nums">{time(r.check_out)}</td>
                        <td className="tabular-nums">{r.worked_minutes ? num(Math.round(r.worked_minutes / 6) / 10) : '—'}</td>
                        <td><Counter value={r.late_minutes} tone="warning" />{r.late_minutes ? ' мин' : ''}</td>
                        <td><LevelBadge level={r.status} label={r.status_label} />{r.adjusted ? <span className="ml-1 text-xs text-ink-muted">испр.</span> : null}</td>
                        <td className="text-xs">{r.check_in ? (r.geo_verified ? `✓ ${r.location ?? 'офис'}${r.distance_m !== null ? `, ${Math.round(r.distance_m)} м` : ''}` : 'вручную') : '—'}</td>
                      </tr>
                    ))}
                  </Table>
                </Section>
              ) : null}
              {view === 'departments' ? (
                <Section title="Статистика отделов" padding={false}>
                  <Table empty={!data.departments.length} headers={['Отдел', 'Посещаемость', 'Пунктуальность', 'Опоздания', 'Отсутствия', 'Часы']}>
                    {data.departments.map((d) => <tr key={d.key}><td className="font-medium">{d.label}</td><td><Progress value={d.attendance_rate} /></td><td><Progress value={d.punctuality_rate} /></td><td>{d.counts.late ?? 0}</td><td><Counter value={d.counts.absent ?? 0} tone="danger" /></td><td>{num(d.worked_hours)}</td></tr>)}
                  </Table>
                </Section>
              ) : null}
              {view === 'employees' ? (
                <Section title="Статистика сотрудников" padding={false}>
                  <Table empty={!data.employees.length} headers={['Сотрудник', 'Рабочих дней', 'Посещаемость', 'Опозданий', 'Минут опозданий', 'Отсутствий', 'Часы']}>
                    {data.employees.map((e) => <tr key={e.user.id}><td><Link to={`/operations/employees/${e.user.id}`} className="font-medium hover:text-brand-700">{e.user.full_name}</Link></td><td>{e.expected_days}</td><td><Progress value={e.attendance_rate} /></td><td>{e.counts.late ?? 0}</td><td>{e.late_minutes}</td><td><Counter value={e.counts.absent ?? 0} tone="danger" /></td><td>{num(e.worked_hours)}</td></tr>)}
                  </Table>
                </Section>
              ) : null}
              <Note>Статусы «Отпуск» и «Удалённо» появятся, когда в LMS начнётся учёт отпусков и удалённой работы: сейчас таких данных нет. Отсутствие прихода не считается нарушением, пока рабочее время по графику не закончилось.</Note>
            </div>
          )
        }}
      </QueryView>
    </div>
  )
}

/** /operations/daily — что произошло за день и кто отвечает за невыполненное. */
export function OperationsDailyPage() {
  const [date, setDate] = useState('')
  const query = useOpsDaily(date || undefined)
  return (
    <div className="space-y-4">
      <PageHeader title="Ежедневный контроль" description="Задачи, отчёты, журналы, посещаемость, KPI, студенты и проблемы за день"
        actions={<div className="flex items-center gap-2 print:hidden"><input type="date" aria-label="День" className="form-control w-44" value={date} max={new Date().toISOString().slice(0, 10)} onChange={(e) => setDate(e.target.value)} /><Button variant="secondary" onClick={() => window.print()}>Печать</Button></div>} />
      <QueryView query={query}>
        {(data) => (
          <div className="space-y-4">
            <p className="text-sm text-ink-secondary">Daily Operations Report за <b>{shortDate(data.date)}</b></p>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
              <StatCard label="Выполнено задач" value={data.tasks.completed_count} />
              <StatCard label="Просрочено" value={data.tasks.overdue_count} tone={data.tasks.overdue_count ? 'danger' : 'default'} />
              <StatCard label="Отчёты сданы" value={data.reports.expected ? `${data.reports.submitted}/${data.reports.expected}` : '—'} />
              <StatCard label="Журналы: проблемы" value={(data.journals.summary.attention_count as number) ?? 0} tone="warning" />
              <StatCard label="Посещаемость" value={pct(data.attendance.attendance_rate)} hint={`опозданий ${data.attendance.counts.late ?? 0}`} />
              <StatCard label="Открытых проблем" value={data.issues.open} hint={`новых: ${data.issues.new_today}`} />
            </div>
            <Section title="По отделам" padding={false}>
              <Table headers={['Отдел', 'Выполнено', 'Просрочено', 'Отчёты не сданы', 'Не пришли', 'Опоздали']}>
                {data.departments.map((d) => <tr key={d.key}><td className="font-medium">{d.label}</td><td>{d.completed}</td><td><Counter value={d.overdue} tone="danger" /></td><td><Counter value={d.reports_missing} tone="danger" /></td><td><Counter value={d.absent} tone="danger" /></td><td><Counter value={d.late} tone="warning" /></td></tr>)}
              </Table>
            </Section>
            <div className="grid gap-4 lg:grid-cols-2">
              <Section title="Невыполненные задачи и ответственные" padding={false}>
                <Table empty={!data.tasks.overdue.length} headers={['Задача', 'Ответственный', 'Дедлайн', 'Приоритет']}>
                  {data.tasks.overdue.map((t) => <tr key={t.id}><td><Link to={`/tasks/${t.id}`} className="hover:text-brand-700">{t.title}</Link></td><td className="text-sm">{t.assignee?.full_name ?? t.department_label}</td><td className="text-sm">{dateTime(t.deadline)}</td><td><PriorityBadge priority={t.priority} label={t.priority_label} /></td></tr>)}
                </Table>
              </Section>
              <Section title="Выполненные задачи" padding={false}>
                <Table empty={!data.tasks.completed.length} headers={['Задача', 'Исполнитель', 'Отдел']}>
                  {data.tasks.completed.map((t) => <tr key={t.id}><td><Link to={`/tasks/${t.id}`} className="hover:text-brand-700">{t.title}</Link></td><td className="text-sm">{t.assignee?.full_name ?? '—'}</td><td className="text-sm">{t.department_label}</td></tr>)}
                </Table>
              </Section>
              <Section title="Несданные отчёты" padding={false}>
                <Table empty={!data.reports.missing.length} headers={['Сотрудник', 'Отчёт', 'Срок']}>
                  {data.reports.missing.map((r, i) => <tr key={i}><td><Link to={`/operations/employees/${r.user.id}`} className="hover:text-brand-700">{r.user.full_name}</Link></td><td>{r.kind === 'daily' ? 'Ежедневный' : r.kind === 'weekly' ? 'Еженедельный' : 'Ежемесячный'}</td><td className="text-sm">{dateTime(r.due)}</td></tr>)}
                </Table>
              </Section>
              <Section title="Журналы занятий: требуют внимания" padding={false}>
                <Table empty={!data.journals.problems.length} headers={['Тренер', 'Группа', 'Статус', 'Что осталось']}>
                  {data.journals.problems.map((r) => <tr key={r.key}><td>{r.teacher ? <Link to={`/operations/trainers/${r.teacher.id}`} className="hover:text-brand-700">{r.teacher.name}</Link> : 'Без тренера'}</td><td>{r.group.name}</td><td><LevelBadge level={r.status} label={r.status_label} /></td><td className="text-xs text-ink-secondary">{r.issues.join('; ')}</td></tr>)}
                </Table>
              </Section>
              <Section title="Посещаемость: отсутствуют и опоздали" padding={false}>
                <Table empty={!data.attendance.absent.length && !data.attendance.late.length} headers={['Сотрудник', 'Статус', 'Приход', 'Опоздание']}>
                  {[...data.attendance.absent, ...data.attendance.late].map((r) => <tr key={`${r.user.id}-${r.status}`}><td>{r.user.full_name}</td><td><LevelBadge level={r.status} label={r.status_label} /></td><td>{time(r.check_in)}</td><td>{r.late_minutes ? `${r.late_minutes} мин` : '—'}</td></tr>)}
                </Table>
              </Section>
              <Section title="Проблемные студенты" padding={false}>
                <Table empty={!data.students.length} headers={['Студент', 'Группа', 'Посещаемость', 'Статус']}>
                  {data.students.map((s) => <tr key={s.student_id}><td>{s.name}</td><td className="text-sm">{s.group?.name ?? '—'}</td><td>{pct(s.attendance)}</td><td><LevelBadge level={s.status} label={s.status_label} /></td></tr>)}
                </Table>
              </Section>
            </div>
            <Section title="Открытые проблемы" padding={false} actions={<Link to="/operations/issues" className="text-sm font-medium text-brand-700 hover:underline">Все проблемы</Link>}>
              <Table empty={!data.issues.items.length} headers={['Проблема', 'Вид', 'Отдел', 'Ответственный', 'Приоритет']}>
                {data.issues.items.map((i) => <tr key={i.id}><td><Link to={`/operations/issues?open=${i.id}`} className="hover:text-brand-700">{i.title}</Link></td><td className="text-sm">{i.kind_label}</td><td className="text-sm">{i.department_label}</td><td className="text-sm">{i.responsible?.full_name ?? '—'}</td><td><PriorityBadge priority={i.priority} label={i.priority} /></td></tr>)}
              </Table>
            </Section>
          </div>
        )}
      </QueryView>
    </div>
  )
}

function formatMetric(value: number | null | undefined, metric: MetricInfo) {
  if (value === null || value === undefined) return '—'
  if (metric.unit === 'percent') return pct(value)
  if (metric.unit === 'money') return num(value, 'сом')
  if (metric.unit === 'minutes') return num(value, 'мин')
  return num(value)
}

function TargetModal({ onClose, metrics, initial }: { onClose: () => void; metrics: MetricInfo[]; initial: KpiTargetInput & { id?: number } }) {
  const meta = useOpsMeta()
  const save = useSaveTarget()
  const { showToast } = useToast()
  const [form, setForm] = useState<KpiTargetInput>(initial)
  const metric = metrics.find((m) => m.key === form.metric)
  const departments = (meta.data?.departments ?? []).filter((d) => !metric || !metric.departments.length || metric.departments.includes(d.value))
  const submit = () => save.mutate({ id: initial.id ?? null, body: form }, {
    onSuccess: () => { showToast('Цель сохранена', 'success'); onClose() },
    onError: (e) => showToast(extractErrorMessage(e), 'error'),
  })
  return (
    <Modal isOpen onClose={onClose} title={initial.id ? 'Изменить цель KPI' : 'Новая цель KPI'}>
      <div className="space-y-3">
        <label className="block"><span className="field-label">Показатель</span>
          <Select value={form.metric ?? ''} placeholder="Выберите показатель" options={metrics.map((m) => ({ value: m.key, label: `${m.label}${m.higher_is_better ? '' : ' (меньше — лучше)'}` }))} onChange={(e) => setForm({ ...form, metric: e.target.value })} /></label>
        <label className="block"><span className="field-label">Сотрудник (пусто — цель отдела)</span>
          <Select value={form.employee ? String(form.employee) : ''} placeholder="Весь отдел" options={(meta.data?.employees ?? []).filter((e) => !metric?.roles.length || metric.roles.includes(e.role)).map((e) => ({ value: String(e.id), label: `${e.full_name} — ${e.role_label}` }))} onChange={(e) => setForm({ ...form, employee: e.target.value ? Number(e.target.value) : null })} /></label>
        {!form.employee ? <label className="block"><span className="field-label">Отдел</span><Select value={form.department ?? ''} placeholder="Выберите отдел" options={departments} onChange={(e) => setForm({ ...form, department: e.target.value as KpiTargetInput['department'] })} /></label> : null}
        <div className="grid grid-cols-2 gap-3">
          <label className="block"><span className="field-label">Период</span><Select value={form.period ?? 'monthly'} options={meta.data?.kpi_periods ?? []} onChange={(e) => setForm({ ...form, period: e.target.value as KpiTargetInput['period'] })} /></label>
          <label className="block"><span className="field-label">Цель{metric ? ` (${metric.unit === 'percent' ? '%' : metric.unit === 'money' ? 'сом' : metric.unit === 'minutes' ? 'мин' : 'шт.'})` : ''}</span><Input type="number" min={0} step="any" value={form.target_value ?? ''} onChange={(e) => setForm({ ...form, target_value: e.target.value })} /></label>
          <label className="block"><span className="field-label">Действует с</span><Input type="date" value={form.valid_from ?? ''} onChange={(e) => setForm({ ...form, valid_from: e.target.value })} /></label>
          <label className="block"><span className="field-label">по (необязательно)</span><Input type="date" value={form.valid_to ?? ''} onChange={(e) => setForm({ ...form, valid_to: e.target.value || null })} /></label>
        </div>
        <label className="block"><span className="field-label">Комментарий</span><Input value={form.note ?? ''} onChange={(e) => setForm({ ...form, note: e.target.value })} /></label>
        <div className="flex justify-end gap-2"><Button variant="ghost" onClick={onClose}>Отмена</Button><Button onClick={submit} isLoading={save.isPending} disabled={!form.metric || !form.target_value}>Сохранить</Button></div>
      </div>
    </Modal>
  )
}

function KpiRow({ m, onHistory }: { m: KpiValue; onHistory: () => void }) {
  return (
    <tr>
      <td><button type="button" onClick={onHistory} className="text-left font-medium hover:text-brand-700">{m.label}</button><span className="block text-xs text-ink-muted">{m.source}</span></td>
      <td className="font-semibold tabular-nums">{formatMetric(m.actual, m)}</td>
      <td className="tabular-nums">{m.target !== null ? formatMetric(m.target, m) : <span className="text-xs text-ink-muted">не задана</span>}</td>
      <td>{m.achievement !== null ? <Progress value={m.achievement} /> : '—'}</td>
      <td className="tabular-nums">{formatMetric(m.previous ?? null, m)}</td>
      <td className="whitespace-nowrap text-sm">{m.trend ? (m.trend.change === null ? (m.trend.direction === 'up' ? '↑' : '—') : <span className={(m.trend.direction === 'up') === m.higher_is_better ? 'text-brand-700' : m.trend.direction === 'stable' ? '' : 'text-danger'}>{m.trend.direction === 'up' ? '↑' : m.trend.direction === 'down' ? '↓' : '→'} {Math.abs(m.trend.change)}%</span>) : '—'}</td>
    </tr>
  )
}

/** /operations/kpi — KPI отделов и сотрудников: цель, факт, достижение,
 * прошлый период, тренд и история. Цели — только из интерфейса. */
export function OperationsKpiPage() {
  const filters = useOpsFilters('this_month')
  const meta = useOpsMeta()
  const query = useOpsKpi(filters.params)
  const targets = useOpsTargets({ department: filters.raw.get('department') ?? undefined })
  const remove = useDeleteTarget()
  const [editing, setEditing] = useState<(KpiTargetInput & { id?: number }) | null>(null)
  const [history, setHistory] = useState<{ metric: string; department?: string; employee?: string; label: string } | null>(null)
  const hist = useOpsKpiHistory({ metric: history?.metric, department: history?.department, employee: history?.employee, period_type: 'monthly' }, history !== null)
  const metrics = (meta.data?.metrics ?? []).filter((m) => !m.financial || meta.data?.can_view_finance)
  return (
    <div className="space-y-4">
      <PageHeader title="KPI и аналитика" description="Показатели каждого отдела и сотрудника из реальных данных LMS"
        actions={<Button leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setEditing({ period: 'monthly', valid_from: new Date().toISOString().slice(0, 10) })}>Цель KPI</Button>} />
      <OpsFilters filters={filters} show={['department', 'employee']} />
      <QueryView query={query}>
        {(data) => (
          <div className="space-y-4">
            <p className="text-sm text-ink-secondary">Период: {data.filters.label} ({shortDate(data.filters.start)} — {shortDate(data.filters.end)}); сравнение с {shortDate(data.previous.start)} — {shortDate(data.previous.end)}. Цели берутся для периода «{data.period_type === 'daily' ? 'день' : data.period_type === 'weekly' ? 'неделя' : 'месяц'}».</p>
            {data.departments.map((d) => (
              <Section key={d.department} title={data.employee ? `${data.employee.full_name}` : d.label} padding={false}>
                <Table empty={!d.metrics.length} headers={['Показатель', 'Факт', 'Цель', 'Достижение', 'Прошлый период', 'Тренд']}>
                  {d.metrics.map((m) => <KpiRow key={m.key} m={m} onHistory={() => setHistory({ metric: m.key, department: data.employee ? undefined : d.department, employee: data.employee ? String(data.employee.id) : undefined, label: m.label })} />)}
                </Table>
              </Section>
            ))}
          </div>
        )}
      </QueryView>
      {history ? (
        <Section title={`История: ${history.label}`} actions={<Button variant="ghost" size="sm" onClick={() => setHistory(null)}>Закрыть</Button>}>
          {hist.data ? (
            <div className="grid gap-4 md:grid-cols-2">
              <TrendChart title={history.label} points={hist.data.history.filter((p) => p.actual !== null).map((p) => ({ label: shortDate(p.start).slice(3), value: p.actual as number }))}
                max={Math.max(100, ...hist.data.history.map((p) => p.actual ?? 0), ...hist.data.history.map((p) => p.target ?? 0))} />
              <Table headers={['Месяц', 'Факт', 'Цель', 'Достижение']}>
                {hist.data.history.map((p) => <tr key={p.start}><td>{shortDate(p.start).slice(3)}</td><td>{num(p.actual)}</td><td>{num(p.target)}</td><td>{pct(p.achievement)}</td></tr>)}
              </Table>
            </div>
          ) : <p className="text-sm text-ink-muted">Загрузка…</p>}
        </Section>
      ) : null}
      <Section title="Цели KPI" padding={false}>
        <Table empty={!targets.data?.results.length} headers={['Показатель', 'Отдел / сотрудник', 'Период', 'Цель', 'Действует', '']}>
          {(targets.data?.results ?? []).map((t) => (
            <tr key={t.id}>
              <td className="font-medium">{t.metric_label}</td>
              <td className="text-sm">{t.employee_info?.full_name ?? t.department_label}</td>
              <td>{t.period_label}</td>
              <td className="tabular-nums">{num(t.target_value)}</td>
              <td className="text-sm">{shortDate(t.valid_from)} — {t.valid_to ? shortDate(t.valid_to) : 'бессрочно'}</td>
              <td className="whitespace-nowrap text-right">
                <Button variant="ghost" size="sm" onClick={() => setEditing({ ...t, employee: t.employee })}>Изменить</Button>
                <Button variant="ghost" size="sm" aria-label="Удалить цель" onClick={() => remove.mutate(t.id)}><Trash2 className="size-4" aria-hidden /></Button>
              </td>
            </tr>
          ))}
        </Table>
      </Section>
      <Note>Нормативы не зашиты в систему: показатель без цели отображается без «достижения» и не создаёт нарушений. Счётчики (продажи, задачи) сравниваются с целью только за завершённый период.</Note>
      {editing ? <TargetModal metrics={metrics} initial={editing} onClose={() => setEditing(null)} /> : null}
    </div>
  )
}
