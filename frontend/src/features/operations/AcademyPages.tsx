import type { ReactNode } from 'react'
import { ArrowLeft } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'

import { TrendChart } from '@/components/charts/TrendChart'
import { AttendanceMatrix } from '@/features/attendanceMatrix/AttendanceMatrix'
import { CourseProgressCell, GroupStudyMonths, StudyMonthCell } from '@/features/academicProgress/ui'

const PROGRAMS_PATH = '/operations/academy/programs'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { StatCard } from '@/components/ui/StatCard'
import { som } from '@/features/accounting/shared'
import {
  useOpsAcademyGroup,
  useOpsAcademyGroups,
  useOpsAcademyMeta,
  useOpsAcademyMonthly,
  useOpsAcademyPerformance,
  useOpsAcademyStudent,
  useOpsAcademyStudents,
} from '@/hooks/useOperations'
import type { OpsPeriod } from '@/types/operations'
import type { AttentionRow } from '@/types/operationsAcademy'

import { LevelBadge, Note, OpsFilters, Progress, QueryView, Section, Table, num, pct, shortDate, useOpsFilters } from './shared'

/* Раздел «Академия» кабинета операционного директора — только просмотр.
 * Цифры приходят с сервера (/operations/academy/…): Reports / KPI,
 * «Прогресс студентов», оплата обучения, рейтинг XP, стипендии. */

const LEVEL_LABEL: Record<string, string> = { good: 'Хороший', attention: 'Требует внимания', low: 'Низкий', no_data: 'Нет данных' }
const MONTH_PERIODS: OpsPeriod[] = ['this_month', 'last_month', 'custom']
const PERIODS: OpsPeriod[] = ['this_week', 'this_month', 'last_month', 'custom']

type Filters = ReturnType<typeof useOpsFilters>
type FilterKey = 'search' | 'program' | 'group' | 'teacher' | 'groupStatus' | 'studentStatus'

function AcademyFilters({ filters, show, periods = PERIODS, children }: { filters: Filters; show: FilterKey[]; periods?: OpsPeriod[]; children?: ReactNode }) {
  const meta = useOpsAcademyMeta()
  const { raw, set } = filters
  const select = (key: string, label: string, placeholder: string, options: { value: string; label: string }[]) => (
    <div className="md:w-52" key={key}>
      <Select aria-label={label} placeholder={placeholder} value={raw.get(key) ?? ''} options={options}
        onChange={(e) => set({ [key]: e.target.value, page: undefined })} />
    </div>
  )
  const ids = (rows?: { id: number; name: string }[]) => (rows ?? []).map((r) => ({ value: String(r.id), label: r.name }))
  return (
    <OpsFilters filters={filters} periods={periods}>
      {show.includes('search') ? (
        <div className="col-span-2 md:w-60"><SearchInput value={raw.get('search') ?? ''} onChange={(v) => set({ search: v, page: undefined })} placeholder="Поиск" /></div>
      ) : null}
      {show.includes('program') ? select('program', 'Программа', 'Все программы', ids(meta.data?.programs)) : null}
      {show.includes('group') ? select('group', 'Группа', 'Все группы', ids(meta.data?.groups)) : null}
      {show.includes('teacher') ? select('teacher', 'Тренер', 'Все тренеры', ids(meta.data?.teachers)) : null}
      {show.includes('groupStatus') ? select('status', 'Статус группы', 'Все статусы', meta.data?.group_statuses ?? []) : null}
      {show.includes('studentStatus') ? select('status', 'Статус студента', 'Все статусы', meta.data?.student_statuses ?? []) : null}
      {children}
    </OpsFilters>
  )
}

function Pager({ page, pages, count, onPage }: { page: number; pages: number; count: number; onPage: (page: number) => void }) {
  if (pages <= 1) return <p className="px-4 py-2 text-xs text-ink-muted">Всего: {count}</p>
  return (
    <div className="flex items-center justify-between gap-2 border-t border-border px-4 py-2 text-sm">
      <span className="text-ink-muted">Всего: {count} · стр. {page} из {pages}</span>
      <div className="flex gap-1">
        <Button variant="ghost" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>Назад</Button>
        <Button variant="ghost" size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>Вперёд</Button>
      </div>
    </div>
  )
}

/** Изменение в процентных пунктах к прошлому периоду. */
function Delta({ value, unit = 'п.п.' }: { value: number | null | undefined; unit?: string }) {
  if (value === null || value === undefined) return <span className="text-ink-muted">—</span>
  const tone = value > 0 ? 'text-brand-700' : value < 0 ? 'text-danger' : 'text-ink-muted'
  return <span className={`tabular-nums ${tone}`}>{value > 0 ? '+' : ''}{value.toLocaleString('ru-RU')} {unit}</span>
}

const deltaText = (value: number | null | undefined) =>
  value === null || value === undefined ? 'нет данных за прошлый период' : `к прошлому периоду ${value > 0 ? '+' : ''}${value.toLocaleString('ru-RU')} п.п.`

function Level({ level }: { level: string | null | undefined }) {
  return level ? <LevelBadge level={level} label={LEVEL_LABEL[level] ?? level} /> : <span className="text-ink-muted">—</span>
}

function BackLink({ to, label }: { to: string; label: string }) {
  return <Link to={to} className="inline-flex items-center gap-1 text-sm text-ink-secondary hover:text-brand-700"><ArrowLeft className="size-4" aria-hidden />{label}</Link>
}

function chartPoints<T extends { month: string }>(rows: T[], pick: (row: T) => number | null) {
  return rows.filter((r) => pick(r) !== null).map((r) => ({ label: r.month.slice(5) + '.' + r.month.slice(2, 4), value: pick(r) as number }))
}

const BADGES_NOTE = 'Бейджей в LMS нет — показываются XP (правила рейтинга) и достижения: утверждённые стипендии.'

// ---------------------------------------------------------------------------
// Группы
// ---------------------------------------------------------------------------

/** /operations/academy/groups */
export function OperationsAcademyGroupsPage() {
  const filters = useOpsFilters('this_month')
  const query = useOpsAcademyGroups(filters.params)
  return (
    <div className="space-y-4">
      <PageHeader title="Группы" description="Все группы академии: тренер, студенты, занятия, посещаемость и успеваемость за период" />
      <AcademyFilters filters={filters} show={['search', 'program', 'teacher', 'groupStatus']} />
      <QueryView query={query}>
        {(data) => (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
              <StatCard label="Групп" value={data.summary.groups} hint={`активных ${data.summary.active}`} />
              <StatCard label="Активных студентов" value={data.summary.students} />
              <StatCard label="Средняя посещаемость" value={pct(data.summary.average_attendance)} />
              <StatCard label="Требуют внимания" value={data.summary.attention} tone={data.summary.attention ? 'warning' : 'default'} hint="KPI «Низкий» или «Требует внимания»" />
              <StatCard label="Период" value={data.filters.label} hint={`${shortDate(data.filters.start)} — ${shortDate(data.filters.end)}`} />
            </div>
            <Section title="Группы" padding={false}>
              <Table empty={!data.results.length} headers={['Группа', 'Программа', 'Тренер', 'Студентов', 'Старт', 'Учебный месяц', 'Общий прогресс курса', 'Посещаемость', 'Успеваемость', 'KPI', 'Статус']}>
                {data.results.map((g) => (
                  <tr key={g.id}>
                    <td><Link to={`/operations/academy/groups/${g.id}`} className="font-medium hover:text-brand-700">{g.name}</Link></td>
                    <td className="text-sm">{g.program}</td>
                    <td className="text-sm">{g.trainer_names}</td>
                    <td className="tabular-nums">{g.students.active}</td>
                    <td className="whitespace-nowrap">{shortDate(g.start_date)}</td>
                    <td><StudyMonthCell progress={g.academic} settingsPath={PROGRAMS_PATH} /></td>
                    <td><CourseProgressCell progress={g.academic} legacy={g.plan} /></td>
                    <td><Progress value={g.attendance_rate} /></td>
                    <td><Progress value={g.progress_rate} /></td>
                    <td><Level level={g.kpi_level} /></td>
                    <td><Badge tone={g.status === 'active' ? 'success' : 'muted'}>{g.status_display}</Badge></td>
                  </tr>
                ))}
              </Table>
              <Pager page={data.page} pages={data.pages} count={data.count} onPage={(p) => filters.set({ page: String(p) })} />
            </Section>
            <Note>Посещаемость, ДЗ, тесты, успеваемость и KPI — из отчётов академии за выбранный период; «Учебный месяц» — по проведённым занятиям и настройкам учебных месяцев программы; «Общий прогресс курса» — проведено из запланированного.</Note>
          </div>
        )}
      </QueryView>
    </div>
  )
}

/** /operations/academy/groups/:id */
export function OperationsAcademyGroupPage() {
  const id = Number(useParams().id)
  const filters = useOpsFilters('this_month')
  const query = useOpsAcademyGroup(id, filters.params)
  return (
    <div className="space-y-4">
      <BackLink to="/operations/academy/groups" label="Все группы" />
      <QueryView query={query}>
        {(d) => (
          <div className="space-y-4">
            <PageHeader title={d.group.name} description={`${d.group.program} · ${d.trainers.map((t) => `${t.name}${t.subject ? ` (${t.subject})` : ''}`).join(', ') || 'тренер не назначен'}`} />
            <OpsFilters filters={filters} periods={PERIODS} />
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
              <StatCard label="Активных студентов" value={d.students.active} hint={`новых ${d.students.new}, ушли ${d.students.left}`} />
              <StatCard label="Старт группы" value={shortDate(d.group.start_date)} hint={d.group.status_display} />
              <StatCard
                label="Учебный месяц"
                value={d.academic.month ? (d.academic.status === 'completed' ? 'Пройден' : d.academic.month.label) : 'Настройка'}
                hint={d.academic.month ? `${d.academic.month.subject?.name ?? ''} ${d.academic.month.done} / ${d.academic.month.planned} · курс ${d.academic.course?.done} / ${d.academic.course?.planned}`.trim() : d.academic.reason || `пройдено ${d.plan.completed}${d.plan.planned ? ` из ${d.plan.planned}` : ''}`}
              />
              <StatCard label="Посещаемость" value={pct(d.attendance.rate)} hint={`${d.attendance.present + d.attendance.late} из ${d.attendance.total} отметок`} />
              <StatCard label="ДЗ выполнено" value={pct(d.homework.completion_rate)} hint={`средний балл ${num(d.homework.average_score)}`} />
              <StatCard label="XP за период" value={num(d.xp_total)} hint={`достижений: ${d.achievements.length}`} />
            </div>
            <Section title="Студенты группы" padding={false}>
              <Table empty={!d.student_progress.length} headers={['Студент', 'Посещаемость', 'Был / пропустил', 'ДЗ', 'Средний балл', 'Тесты', 'К прошлому периоду', 'XP', 'Достижения']}>
                {d.student_progress.map((s) => (
                  <tr key={s.id}>
                    <td><Link to={`/operations/academy/students/${s.id}`} className="font-medium hover:text-brand-700">{s.name}</Link>{!s.in_group_now ? <span className="block text-xs text-ink-muted">сейчас не в группе</span> : null}</td>
                    <td><Progress value={s.attendance_rate} /></td>
                    <td className="tabular-nums">{s.attended} / {s.absences}</td>
                    <td><Progress value={s.homework_rate} /></td>
                    <td className="tabular-nums">{num(s.average_score)}</td>
                    <td className="tabular-nums">{s.tests_count ? `${num(s.test_average)} (${s.tests_count})` : '—'}</td>
                    <td><Delta value={s.change.attendance_rate} /></td>
                    <td className="tabular-nums">{s.xp ?? 0}</td>
                    <td className="tabular-nums">{s.achievements ?? 0}</td>
                  </tr>
                ))}
              </Table>
            </Section>
            <Section title="Учебные месяцы" actions={<Link to={PROGRAMS_PATH} className="text-sm font-medium text-brand-700 hover:underline">Настройки программы</Link>}>
              <GroupStudyMonths groupId={d.group.id} settingsPath={PROGRAMS_PATH} />
            </Section>
            {/* Полноценная таблица посещаемости по датам занятий — та же, что у ассистента и Team Lead. */}
            <Section
              title="Посещаемость по датам занятий"
              actions={<Link to={`/operations/attendance?group=${d.group.id}`} className="text-sm font-medium text-brand-700 hover:underline">Открыть отдельно</Link>}
            >
              <AttendanceMatrix groupId={d.group.id} />
            </Section>
            <div className="grid gap-4 lg:grid-cols-2">
              <Section title="Расписание" padding={false}>
                <Table empty={!d.schedule.length} headers={['День', 'Время', 'Предмет', 'Тренер', 'Кабинет']}>
                  {d.schedule.map((s, i) => <tr key={i} className={s.is_active ? '' : 'opacity-60'}><td>{s.day}</td><td className="tabular-nums">{s.start}–{s.end}</td><td>{s.subject ?? '—'}</td><td className="text-sm">{s.trainer ?? '—'}</td><td>{s.room ?? '—'}</td></tr>)}
                </Table>
              </Section>
              <Section title="Посещаемость и ДЗ за период">
                <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
                  {([['Был', d.attendance.present], ['Опоздал', d.attendance.late], ['Пропустил', d.attendance.absent], ['Уважительная', d.attendance.excused],
                    ['ДЗ задано', d.homework.assigned], ['ДЗ сдано', d.homework.submitted], ['ДЗ не сдано', d.homework.not_submitted]] as const).map(([label, value]) => (
                    <div key={label} className="rounded-lg bg-surface-muted px-3 py-2"><dt className="text-xs text-ink-secondary">{label}</dt><dd className="font-semibold tabular-nums">{value}</dd></div>
                  ))}
                </dl>
              </Section>
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <Section title="Тесты и экзамены" padding={false}>
                <div className="grid grid-cols-2 gap-3 p-4 text-sm">
                  <div><p className="text-xs text-ink-secondary">Тесты</p><p className="font-semibold">{num(d.assessments.tests.average_score)} · сдали {pct(d.assessments.tests.pass_rate)}</p><p className="text-xs text-ink-muted">попыток {d.assessments.tests.attempts}</p></div>
                  <div><p className="text-xs text-ink-secondary">Экзамены</p><p className="font-semibold">{num(d.assessments.exams.average_score)} · сдали {pct(d.assessments.exams.pass_rate)}</p><p className="text-xs text-ink-muted">попыток {d.assessments.exams.attempts}</p></div>
                </div>
                <Table empty={!d.assessments.sessions.length} headers={['Сессия', 'Тип', 'Попыток', 'Сдали', 'Средний балл']}>
                  {d.assessments.sessions.map((s) => <tr key={s.id}><td>{s.title}</td><td>{s.type === 'exam' ? 'Экзамен' : 'Тест'}</td><td>{s.attempts}</td><td>{s.passed}</td><td>{num(s.average_score)}</td></tr>)}
                </Table>
              </Section>
              <Section title="Достижения студентов">
                {d.achievements.length ? (
                  <ul className="space-y-2 text-sm">{d.achievements.map((a, i) => <li key={i} className="flex justify-between gap-2"><span><span className="font-medium">{a.student}</span> — {a.title}</span><span className="text-ink-muted">{shortDate(a.date)}</span></li>)}</ul>
                ) : <p className="text-sm text-ink-muted">За период достижений нет.</p>}
                <p className="mt-3 text-xs text-ink-muted">{BADGES_NOTE}</p>
              </Section>
            </div>
            <Section title="Помесячный прогресс">
              <div className="grid gap-4 md:grid-cols-2">
                <TrendChart title="Посещаемость, %" points={chartPoints(d.monthly, (m) => m.attendance_rate)} max={100} valueSuffix="%" />
                <TrendChart title="Выполнение ДЗ, %" points={chartPoints(d.monthly, (m) => m.homework_rate)} max={100} valueSuffix="%" color="var(--color-info)" />
              </div>
              <Table headers={['Месяц', 'Студентов', 'Посещаемость', 'ДЗ', 'Тесты', 'KPI']}>
                {d.monthly.map((m) => <tr key={m.month}><td>{m.month}</td><td>{m.students ?? '—'}</td><td>{pct(m.attendance_rate)}</td><td>{pct(m.homework_rate)}</td><td>{num(m.test_score_rate)}</td><td>{num(m.kpi)}</td></tr>)}
              </Table>
            </Section>
            <Section title="История занятий" padding={false}>
              <Table empty={!d.lesson_history.length} headers={['Дата', '№', 'Тема', 'Предмет', 'Тренер', 'Отмечено / были', 'Статус']}>
                {d.lesson_history.map((l) => <tr key={l.id}><td className="whitespace-nowrap">{shortDate(l.date)} {l.start ?? ''}</td><td>{l.number ?? '—'}</td><td className="text-sm">{l.topic || '—'}</td><td>{l.subject ?? '—'}</td><td className="text-sm">{l.trainer ?? '—'}</td><td className="tabular-nums">{l.attendance.marked} / {l.attendance.attended}</td><td><Badge tone={l.status === 'completed' ? 'success' : l.status === 'cancelled' ? 'danger' : 'muted'}>{l.status_display}</Badge></td></tr>)}
              </Table>
            </Section>
          </div>
        )}
      </QueryView>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Студенты
// ---------------------------------------------------------------------------

/** /operations/academy/students */
export function OperationsAcademyStudentsPage() {
  const filters = useOpsFilters('this_month')
  const query = useOpsAcademyStudents(filters.params)
  return (
    <div className="space-y-4">
      <PageHeader title="Студенты" description="Справочник студентов: группа, тренер, договор и оплаты, посещаемость и успеваемость за период" />
      <AcademyFilters filters={filters} show={['search', 'program', 'group', 'teacher', 'studentStatus']} />
      <QueryView query={query}>
        {(data) => (
          <Section title="Студенты" padding={false}>
            <Table empty={!data.results.length} headers={['Студент', 'Группа', 'Программа', 'Тренер', 'Зачислен', ...(data.finance_visible ? ['Договор', 'Оплачено', 'Долг'] : []), 'Посещаемость', 'Успеваемость', 'Статус']}>
              {data.results.map((s) => (
                <tr key={s.id}>
                  <td><Link to={`/operations/academy/students/${s.id}`} className="font-medium hover:text-brand-700">{s.name}</Link></td>
                  <td className="text-sm">{s.group ? <Link to={`/operations/academy/groups/${s.group.id}`} className="hover:text-brand-700">{s.group.name}</Link> : '—'}</td>
                  <td className="text-sm">{s.program ?? '—'}</td>
                  <td className="text-sm">{s.trainers.join(', ') || '—'}</td>
                  <td className="whitespace-nowrap">{shortDate(s.enrollment_date)}</td>
                  {data.finance_visible ? <>
                    <td className="whitespace-nowrap tabular-nums">{s.finance ? som(s.finance.contract_amount) : <span className="text-xs text-ink-muted">нет договора</span>}</td>
                    <td className="whitespace-nowrap tabular-nums">{s.finance ? som(s.finance.paid) : '—'}</td>
                    <td className={`whitespace-nowrap tabular-nums ${s.finance && Number(s.finance.debt) > 0 ? 'font-semibold text-danger' : ''}`}>{s.finance ? som(s.finance.debt) : '—'}</td>
                  </> : null}
                  <td><Progress value={s.attendance_rate} /></td>
                  <td><Level level={s.level} /></td>
                  <td><Badge tone={s.status === 'active' ? 'success' : 'muted'}>{s.status_display}</Badge></td>
                </tr>
              ))}
            </Table>
            <Pager page={data.page} pages={data.pages} count={data.count} onPage={(p) => filters.set({ page: String(p) })} />
          </Section>
        )}
      </QueryView>
      <Note>Договор, оплачено и долг — из оплаты обучения (те же суммы, что в карточке договора бухгалтерии), только просмотр.</Note>
    </div>
  )
}

/** /operations/academy/students/:id — профиль студента, только просмотр. */
export function OperationsAcademyStudentPage() {
  const id = Number(useParams().id)
  const filters = useOpsFilters('this_month')
  const query = useOpsAcademyStudent(id, filters.params)
  return (
    <div className="space-y-4">
      <BackLink to="/operations/academy/students" label="Все студенты" />
      <QueryView query={query}>
        {(d) => {
          const a = d.academic
          const missed = a.attendance_total - a.attended
          return (
            <div className="space-y-4">
              <PageHeader title={d.student.name}
                description={[d.student.group?.name, d.student.program, d.student.trainers.map((t) => t.name).join(', '), `зачислен ${shortDate(d.student.enrollment_date)}`, d.student.status_display].filter(Boolean).join(' · ')} />
              <OpsFilters filters={filters} periods={PERIODS} />
              <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
                <StatCard label="Посещено занятий" value={a.attended} hint={`пропущено ${missed}`} />
                <StatCard label="Посещаемость" value={pct(a.attendance_rate)} hint={a.period ? deltaText(a.period.change.attendance_rate) : undefined} />
                <StatCard label="ДЗ выполнено" value={pct(a.homework_rate)} hint={`${a.homework_submitted} из ${a.homework_results}`} />
                <StatCard label="Средний балл ДЗ" value={num(a.average_score)} />
                <StatCard label="Тесты / экзамены" value={`${num(a.assessments.tests.average_score)} / ${num(a.assessments.exams.average_score)}`} hint={`попыток ${a.assessments.tests.attempts} / ${a.assessments.exams.attempts}`} />
                <StatCard label="XP за период" value={a.xp.total} hint={`посещ. ${a.xp.attendance} · ДЗ ${a.xp.homework} · тесты ${a.xp.tests}`} />
              </div>
              <div className="grid gap-4 lg:grid-cols-3">
                <Section title="Успеваемость" className="lg:col-span-2">
                  <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                    <div><dt className="text-xs text-ink-secondary">Уровень</dt><dd><Level level={a.level} /></dd></div>
                    <div><dt className="text-xs text-ink-secondary">Прогресс</dt><dd className="font-semibold">{pct(a.progress_rate)}</dd></div>
                    <div><dt className="text-xs text-ink-secondary">ДЗ к прошлому периоду</dt><dd><Delta value={a.period?.change.homework_rate} /></dd></div>
                    <div><dt className="text-xs text-ink-secondary">Балл к прошлому периоду</dt><dd><Delta value={a.period?.change.average_score} unit="" /></dd></div>
                  </dl>
                </Section>
                <Section title="Достижения">
                  {a.achievements.length ? <ul className="space-y-1 text-sm">{a.achievements.map((x, i) => <li key={i}>{x.title} <span className="text-ink-muted">· {shortDate(x.date)}</span></li>)}</ul>
                    : <p className="text-sm text-ink-muted">Пока нет.</p>}
                  <p className="mt-2 text-xs text-ink-muted">{BADGES_NOTE}</p>
                </Section>
              </div>
              {d.finance ? (
                <Section title="Договор и оплаты (только просмотр)">
                  {d.finance.contracts.length ? (
                    <div className="space-y-3">
                      {d.finance.contracts.map((c) => (
                        <div key={c.id} className="rounded-lg border border-border p-3">
                          <p className="text-sm font-medium">{[c.program, c.subject, c.plan].filter(Boolean).join(' · ')} <Badge tone={c.status === 'active' ? 'success' : 'muted'}>{c.status_display}</Badge></p>
                          <dl className="mt-2 grid grid-cols-2 gap-2 text-sm sm:grid-cols-5">
                            {([['Стоимость по договору', som(c.original)], ['Скидка', som(c.discount)], ['Итого по договору', som(c.final)], ['Оплачено', som(c.paid)], ['Долг', som(c.debt)]] as const).map(([label, value]) => (
                              <div key={label} className="rounded-lg bg-surface-muted px-3 py-2"><dt className="text-xs text-ink-secondary">{label}</dt><dd className="font-semibold tabular-nums">{value}</dd></div>
                            ))}
                          </dl>
                          {c.discount_reason ? <p className="mt-1 text-xs text-ink-muted">Основание скидки: {c.discount_reason}</p> : null}
                        </div>
                      ))}
                    </div>
                  ) : <p className="text-sm text-ink-muted">Договора нет.</p>}
                  <h3 className="mb-2 mt-4 text-sm font-semibold">История оплат</h3>
                  <Table empty={!d.finance.payments.length} headers={['Дата', 'Тип', 'Сумма', 'Способ', 'Статус', 'Комментарий']}>
                    {d.finance.payments.map((p) => <tr key={p.id}><td className="whitespace-nowrap">{shortDate(p.date)}</td><td>{p.kind_display}</td><td className="whitespace-nowrap tabular-nums">{som(p.amount)}</td><td>{p.method_display}</td><td><Badge tone={p.status === 'confirmed' ? 'success' : 'muted'}>{p.status_display}</Badge></td><td className="text-sm text-ink-secondary">{p.comment || '—'}</td></tr>)}
                  </Table>
                </Section>
              ) : null}
              <Section title="Занятия за период" padding={false}>
                <Table empty={!a.lessons.length} headers={['Дата', 'Тема', 'Предмет', 'Посещение', 'ДЗ', 'Балл']}>
                  {a.lessons.map((l) => <tr key={l.id}><td className="whitespace-nowrap">{shortDate(l.date)}</td><td className="text-sm">{l.topic || '—'}</td><td>{l.subject ?? '—'}</td><td>{l.attendance_display ?? 'не отмечено'}</td><td className="text-sm">{l.homework.map((h) => h.status_display).join(', ') || '—'}</td><td>{l.homework.map((h) => h.score ?? '—').join(', ') || '—'}</td></tr>)}
                </Table>
              </Section>
              <div className="grid gap-4 lg:grid-cols-2">
                <Section title="Тесты и экзамены" padding={false}>
                  <Table empty={!a.tests.length} headers={['Дата', 'Тест', 'Балл', 'Результат']}>
                    {a.tests.map((t) => <tr key={t.id}><td>{shortDate(t.date)}</td><td>{t.title}</td><td>{num(t.score)}</td><td>{t.passed === null ? '—' : t.passed ? 'сдал' : 'не сдал'}</td></tr>)}
                  </Table>
                </Section>
                <Section title="История обучения" padding={false}>
                  <Table empty={!d.history.length} headers={['Дата', 'Событие', 'Группа']}>
                    {d.history.map((h, i) => <tr key={i}><td>{shortDate(h.date)}</td><td>{h.type_display}</td><td className="text-sm">{h.from_group ? `${h.from_group} → ` : ''}{h.group ?? '—'}</td></tr>)}
                  </Table>
                </Section>
              </div>
            </div>
          )
        }}
      </QueryView>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Успеваемость
// ---------------------------------------------------------------------------

/** /operations/academy/performance */
export function OperationsAcademyPerformancePage() {
  const filters = useOpsFilters('this_month')
  const query = useOpsAcademyPerformance(filters.params)
  return (
    <div className="space-y-4">
      <PageHeader title="Успеваемость" description="Месячные показатели студентов и сравнение с прошлым периодом" />
      <AcademyFilters filters={filters} show={['program', 'group', 'teacher']} periods={MONTH_PERIODS}>
        <div className="md:w-52">
          <Select aria-label="Сортировка" value={filters.raw.get('ordering') ?? 'name'} onChange={(e) => filters.set({ ordering: e.target.value })}
            options={[{ value: 'name', label: 'По имени' }, { value: 'attendance', label: 'Посещаемость ↑' }, { value: 'homework', label: 'ДЗ ↑' }, { value: 'xp', label: 'XP ↓' }, { value: 'change', label: 'Снижение посещаемости' }]} />
        </div>
      </AcademyFilters>
      <QueryView query={query}>
        {(d) => {
          const i = d.indicators
          return (
            <div className="space-y-4">
              <p className="text-sm text-ink-secondary">{d.filters.label}: {shortDate(d.filters.start)} — {shortDate(d.filters.end)}; сравнение с {shortDate(d.previous_period.start)} — {shortDate(d.previous_period.end)}.</p>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
                <StatCard label="Посещаемость" value={pct(i.attendance_rate)} hint={deltaText(d.change.attendance_rate)} />
                <StatCard label="Посещено занятий" value={i.attended} hint={`в прошлом периоде ${d.previous.attended}`} />
                <StatCard label="Пропущено занятий" value={i.missed} tone={i.missed > d.previous.missed ? 'warning' : 'default'} hint={`в прошлом периоде ${d.previous.missed}`} />
                <StatCard label="Выполнение ДЗ" value={pct(i.homework_rate)} hint={deltaText(d.change.homework_rate)} />
                <StatCard label="Средний балл тестов" value={num(i.test_average)} hint={deltaText(d.change.test_average)} />
                <StatCard label="Экзамены" value={i.exams.attempts ? `${num(i.exams.average_score)} · ${pct(i.exams.pass_rate)}` : '—'} hint={`попыток ${i.exams.attempts}, сдали ${i.exams.passed}`} />
                <StatCard label="Активность студентов" value={pct(i.activity_rate)} hint={`посетили занятия: ${i.active_students} из ${i.students} · ${deltaText(d.change.activity_rate)}`} />
                <StatCard label="XP" value={num(i.xp)} hint={`в прошлом периоде ${num(d.previous.xp)}`} />
                <StatCard label="Достижения" value={i.achievements} hint="утверждённые стипендии" />
                <StatCard label="Успеваемость" value={pct(i.progress_rate)} hint={`средний балл ДЗ · ${deltaText(d.change.progress_rate)}`} />
              </div>
              <Section title="Студенты" padding={false}>
                <Table empty={!d.results.length} headers={['Студент', 'Группа', 'Посещаемость', 'Был / пропустил', 'ДЗ', 'Балл', 'Посещ. к прошл.', 'ДЗ к прошл.', 'XP', 'Достижения', 'Уровень']}>
                  {d.results.map((r) => (
                    <tr key={r.id}>
                      <td><Link to={`/operations/academy/students/${r.id}`} className="font-medium hover:text-brand-700">{r.name}</Link></td>
                      <td className="text-sm">{r.group}</td>
                      <td><Progress value={r.attendance_rate} /></td>
                      <td className="tabular-nums">{r.attended} / {r.missed}</td>
                      <td><Progress value={r.homework_rate} /></td>
                      <td className="tabular-nums">{num(r.average_score)}</td>
                      <td><Delta value={r.change.attendance_rate} /></td>
                      <td><Delta value={r.change.homework_rate} /></td>
                      <td className="tabular-nums">{r.xp}</td>
                      <td className="tabular-nums">{r.achievements}</td>
                      <td><Level level={r.level} /></td>
                    </tr>
                  ))}
                </Table>
                <Pager page={d.page} pages={d.pages} count={d.count} onPage={(p) => filters.set({ page: String(p) })} />
              </Section>
              <Note>{BADGES_NOTE} Пропуск — отметка «Отсутствовал» или «Уважительная причина»; неотмеченное занятие пропуском не считается.</Note>
            </div>
          )
        }}
      </QueryView>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Месячные результаты
// ---------------------------------------------------------------------------

export function AttentionTable({ rows }: { rows: AttentionRow[] }) {
  return (
    <Table empty={!rows.length} headers={['Студент', 'Группа', 'Посещаемость', 'ДЗ', 'Почему требует внимания', 'Статус']}>
      {rows.map((r) => (
        <tr key={r.id}>
          <td><Link to={`/operations/academy/students/${r.id}`} className="font-medium hover:text-brand-700">{r.name}</Link></td>
          <td className="text-sm">{r.group_id ? <Link to={`/operations/academy/groups/${r.group_id}`} className="hover:text-brand-700">{r.group}</Link> : '—'}</td>
          <td className="tabular-nums">{pct(r.attendance_rate)}</td>
          <td className="tabular-nums">{pct(r.homework_rate)}</td>
          <td className="text-sm"><ul className="list-disc space-y-0.5 pl-4">{r.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></td>
          <td><LevelBadge level={r.status === 'risk' || r.status === 'low' ? 'problem' : 'attention'} label={r.status_display} /></td>
        </tr>
      ))}
    </Table>
  )
}

/** /operations/academy/monthly */
export function OperationsAcademyMonthlyPage() {
  const filters = useOpsFilters('this_month')
  const query = useOpsAcademyMonthly(filters.params)
  return (
    <div className="space-y-4">
      <PageHeader title="Месячные результаты" description="Студенты, посещаемость, успеваемость и достижения академии — за месяц и в динамике" />
      <AcademyFilters filters={filters} show={['program', 'group', 'teacher']} periods={MONTH_PERIODS} />
      <QueryView query={query}>
        {(d) => {
          const i = d.indicators
          const maxActive = Math.max(1, ...d.dynamics.map((m) => m.active))
          return (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
                <StatCard label="Активных студентов" value={i.active_students} hint={`групп ${i.groups}`} />
                <StatCard label="Новые студенты" value={i.new_students} />
                <StatCard label="Ушли" value={i.left_students} tone={i.left_students ? 'warning' : 'default'} hint={`вернулись ${i.returned_students}`} />
                <StatCard label="Переведены между группами" value={i.transferred_students} />
                <StatCard label="Средняя посещаемость" value={pct(i.attendance_rate)} />
                <StatCard label="Успеваемость" value={pct(i.academic_performance)} hint={`KPI ${num(i.kpi)} · тесты ${num(i.test_average)}`} />
                <StatCard label="Выполнение ДЗ" value={pct(i.homework_rate)} />
                <StatCard label="Достижения" value={i.achievements} hint={`XP ${num(i.xp)}`} />
                <StatCard label="Требуют внимания" value={i.attention} tone={i.attention ? 'danger' : 'default'} />
                <StatCard label="Период" value={d.filters.label} hint={`${shortDate(d.filters.start)} — ${shortDate(d.filters.end)}`} />
              </div>
              <Section title="Динамика за 6 месяцев">
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                  <TrendChart title="Посещаемость, %" points={chartPoints(d.dynamics, (m) => m.attendance_rate)} max={100} valueSuffix="%" />
                  <TrendChart title="Успеваемость, %" points={chartPoints(d.dynamics, (m) => m.progress_rate)} max={100} valueSuffix="%" color="var(--color-info)" />
                  <TrendChart title="Выполнение ДЗ, %" points={chartPoints(d.dynamics, (m) => m.homework_rate)} max={100} valueSuffix="%" color="var(--color-warning)" />
                  <TrendChart title="Активные студенты" points={chartPoints(d.dynamics, (m) => m.active)} max={maxActive} />
                </div>
                <Table headers={['Месяц', 'Активных', 'Новых', 'Ушли', 'Посещаемость', 'Успеваемость', 'ДЗ', 'Тесты']}>
                  {d.dynamics.map((m) => <tr key={m.month}><td>{m.month}</td><td className="tabular-nums">{m.active}</td><td className="tabular-nums text-brand-700">+{m.new}</td><td className="tabular-nums text-danger">{m.left ? `−${m.left}` : '0'}</td><td>{pct(m.attendance_rate)}</td><td>{pct(m.progress_rate)}</td><td>{pct(m.homework_rate)}</td><td>{num(m.test_average)}</td></tr>)}
                </Table>
              </Section>
              <Section title="Сравнение групп" padding={false}>
                <Table empty={!d.groups.length} headers={['Группа', 'Программа', 'Студентов', 'Посещаемость', 'ДЗ', 'Тесты', 'KPI']}>
                  {[...d.groups].sort((a, b) => (b.kpi ?? -1) - (a.kpi ?? -1)).map((g) => <tr key={g.id}><td><Link to={`/operations/academy/groups/${g.id}`} className="font-medium hover:text-brand-700">{g.name}</Link></td><td className="text-sm">{g.program}</td><td>{g.students}</td><td><Progress value={g.attendance_rate} /></td><td><Progress value={g.homework_rate} /></td><td>{num(g.test_score_rate)}</td><td><Level level={g.kpi_level} /></td></tr>)}
                </Table>
              </Section>
              <Section title={`Требуют внимания · ${d.attention.length}`} padding={false}>
                <AttentionTable rows={d.attention} />
              </Section>
              <Note>Пороги — из настроек «Контроля активности» (низкая посещаемость &lt; {d.thresholds.low_attendance}%, ДЗ &lt; {d.thresholds.low_homework}%, частые пропуски от {d.thresholds.frequent_absences}, тесты &lt; {d.thresholds.low_test_score}, снижение от {d.thresholds.decline_points} п.п.). {BADGES_NOTE}</Note>
            </div>
          )
        }}
      </QueryView>
    </div>
  )
}
