import { useEffect, useRef, useState } from 'react'
import { AlertCircle, AlertTriangle, ArrowLeft, BookX, CalendarDays, ChevronLeft, ChevronRight, Download, Percent, Settings2, UserX } from 'lucide-react'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { useToast } from '@/components/ui/Toast'
import { attendanceMatrixApi } from '@/api/attendanceMatrix'
import { useMatrixMeta, useMatrixOverview, useMatrixSettings, useUpdateMatrixSettings } from '@/hooks/useAttendanceMatrix'
import { extractErrorMessage } from '@/lib/apiError'
import type { MatrixSettings, Overview, OverviewParams } from '@/types/attendanceMatrix'
import { cn } from '@/utils/cn'

import { AttendanceMatrix } from './AttendanceMatrix'
import { LEVEL_STYLE, SummaryCard, WarningDot, formatDateTime, monthAnchor, pct, percentTone, shortDate, todayIso } from './ui'

type View = 'groups' | 'trainers' | 'students' | 'excused' | 'assistants' | 'history'

/**
 * «Посещаемость и ДЗ» across groups: a Team Lead sees the groups of their
 * directions, the Operations director and Admin the whole academy (backend:
 * apps.attendance_matrix.access). A group opens its full monthly matrix.
 */
export function AttendanceOverviewPage({ title = 'Посещаемость и ДЗ' }: { title?: string }) {
  const [date, setDate] = useState(monthAnchor(todayIso()))
  const [subject, setSubject] = useState('')
  const [teacher, setTeacher] = useState('')
  const [group, setGroup] = useState('')
  const [view, setView] = useState<View>('groups')
  const [openGroup, setOpenGroup] = useState<number | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [exporting, setExporting] = useState(false)
  const { showToast } = useToast()

  const meta = useMatrixMeta()
  const params: OverviewParams = {
    date,
    subject: subject ? Number(subject) : undefined,
    teacher: teacher ? Number(teacher) : undefined,
    group: group ? Number(group) : undefined,
  }
  const { data, isPending, isError, refetch, isFetching } = useMatrixOverview(params, openGroup === null)

  // Opening a group (or going back) starts at the top — not on the first render.
  const mounted = useRef(false)
  useEffect(() => {
    if (mounted.current) window.scrollTo?.({ top: 0 })
    mounted.current = true
  }, [openGroup])

  if (openGroup !== null) {
    return (
      <div>
        <button type="button" onClick={() => setOpenGroup(null)} className="mb-4 inline-flex items-center gap-1.5 text-sm font-medium text-brand-700 hover:underline">
          <ArrowLeft className="size-4" aria-hidden />Все группы
        </button>
        <AttendanceMatrix groupId={openGroup} />
      </div>
    )
  }

  const onExport = async () => {
    setExporting(true)
    try {
      await attendanceMatrixApi.exportOverview(params)
    } catch (error) {
      showToast(extractErrorMessage(error, 'Не удалось сформировать Excel'), 'error')
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title={title}
        description="Посещаемость и домашние задания по группам, тренерам и студентам за месяц"
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" leftIcon={<Settings2 className="size-4" aria-hidden />} onClick={() => setSettingsOpen(true)}>Пороги</Button>
            <Button variant="secondary" leftIcon={<Download className="size-4" aria-hidden />} isLoading={exporting} onClick={() => void onExport()}>Экспорт</Button>
          </div>
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <label className="relative flex h-10 items-center gap-2 rounded-lg border border-border bg-surface px-3 text-sm font-medium text-ink">
          <CalendarDays className="size-4 text-ink-muted" aria-hidden />
          <span>{data?.period.label ?? '…'}</span>
          <input aria-label="Месяц" type="month" value={date.slice(0, 7)} onChange={(e) => e.target.value && setDate(`${e.target.value}-01`)} className="absolute inset-0 cursor-pointer opacity-0" />
        </label>
        <div className="flex h-10 items-center rounded-lg border border-border bg-surface">
          <button type="button" aria-label="Предыдущий месяц" disabled={!data} onClick={() => data && setDate(data.period.prev)} className="flex h-full w-10 items-center justify-center text-ink-secondary hover:bg-surface-hover">
            <ChevronLeft className="size-4" aria-hidden />
          </button>
          <button type="button" aria-label="Следующий месяц" disabled={!data} onClick={() => data && setDate(data.period.next)} className="flex h-full w-10 items-center justify-center border-l border-border text-ink-secondary hover:bg-surface-hover">
            <ChevronRight className="size-4" aria-hidden />
          </button>
        </div>
        <div className="grid min-w-0 flex-1 grid-cols-1 gap-3 sm:grid-cols-3">
          <Select aria-label="Направление" placeholder="Все направления" value={subject} onChange={(e) => setSubject(e.target.value)}
            options={(meta.data?.subjects ?? []).map((s) => ({ value: String(s.id), label: s.name }))} />
          <Select aria-label="Тренер" placeholder="Все тренеры" value={teacher} onChange={(e) => setTeacher(e.target.value)}
            options={(meta.data?.teachers ?? []).map((t) => ({ value: String(t.id), label: t.name }))} />
          <Select aria-label="Группа" placeholder="Все группы" value={group} onChange={(e) => setGroup(e.target.value)}
            options={(meta.data?.groups ?? []).map((g) => ({ value: String(g.id), label: g.name }))} />
        </div>
      </div>

      {isPending ? <LoadingState label="Считаем посещаемость…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}
      {data ? (
        <div className={cn('space-y-5 transition-opacity', isFetching && 'opacity-60')}>
          <OverviewCards data={data} />
          <Trend data={data} />
          <div className="flex gap-1 overflow-x-auto border-b border-border" role="tablist">
            {([
              ['groups', `Группы (${data.groups.length})`],
              ['trainers', `Тренеры (${data.trainers.length})`],
              ['students', `Проблемные студенты (${data.problem_students.length})`],
              ['excused', `Уважительные причины (${data.excused.length})`],
              ['assistants', `Ассистенты (${data.assistants.length})`],
              ['history', 'Журнал изменений'],
            ] as const).map(([key, label]) => (
              <button key={key} type="button" role="tab" aria-selected={view === key} onClick={() => setView(key)}
                className={cn('-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium', view === key ? 'border-brand-500 text-brand-700' : 'border-transparent text-ink-secondary hover:text-ink')}>
                {label}
              </button>
            ))}
          </div>
          {view === 'groups' ? <GroupsTable data={data} onOpen={setOpenGroup} /> : null}
          {view === 'trainers' ? <TrainersTable data={data} /> : null}
          {view === 'students' ? <ProblemStudents data={data} onOpen={setOpenGroup} /> : null}
          {view === 'excused' ? <ExcusedTable data={data} onOpen={setOpenGroup} /> : null}
          {view === 'assistants' ? <AssistantsTable data={data} /> : null}
          {view === 'history' ? <Journal data={data} onOpen={setOpenGroup} /> : null}
        </div>
      ) : null}

      <SettingsModal isOpen={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  )
}

function OverviewCards({ data }: { data: Overview }) {
  const s = data.summary
  const critical = data.problem_students.filter((p) => p.level === 'critical').length
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <SummaryCard tone="green" icon={<Percent className="size-6 text-brand-700" aria-hidden />} label="Общая посещаемость" value={<span className={percentTone(s.percent)}>{pct(s.percent)}</span>} hint={`${s.present} из ${s.marked} отметок · ${s.groups ?? 0} групп`} />
      <SummaryCard tone="red" icon={<UserX className="size-6 text-danger" aria-hidden />} label="Пропуски" value={s.absent} hint={`без причины · уважительных: ${s.excused}`} />
      <SummaryCard tone="gray" icon={<BookX className="size-6 text-ink-secondary" aria-hidden />} label="Несданных ДЗ" value={s.hw_missed} hint={`сдано ${pct(s.hw_percent)}`} />
      <SummaryCard tone="yellow" icon={<AlertTriangle className="size-6 text-warning" aria-hidden />} label="Критичных студентов" value={critical} hint={`требуют внимания: ${data.problem_students.length}`} />
    </div>
  )
}

function Trend({ data }: { data: Overview }) {
  return (
    <section className="card p-4">
      <h3 className="mb-3 text-sm font-semibold text-ink">Динамика посещаемости по месяцам</h3>
      <div className="flex h-36 items-end gap-3">
        {data.trend.map((m) => (
          <div key={`${m.year}-${m.month}`} className="flex min-w-0 flex-1 flex-col items-center gap-1">
            <span className={cn('text-xs font-semibold', percentTone(m.percent))}>{pct(m.percent)}</span>
            <div className="flex h-24 w-full max-w-14 items-end rounded-md bg-surface-muted">
              <div className="w-full rounded-md bg-brand-500" style={{ height: `${m.percent ?? 0}%` }} title={`${m.label}: ${pct(m.percent)}, отметок ${m.marked}`} />
            </div>
            <span className="truncate text-xs text-ink-muted">{m.label}</span>
          </div>
        ))}
      </div>
    </section>
  )
}

function Bar({ value }: { value: number | null }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-surface-hover">
        <div className={cn('h-full rounded-full', value === null ? '' : value >= 85 ? 'bg-brand-500' : value >= 70 ? 'bg-warning' : 'bg-danger')} style={{ width: `${value ?? 0}%` }} />
      </div>
      <span className={cn('w-10 text-right font-semibold', percentTone(value))}>{pct(value)}</span>
    </div>
  )
}

const TH = 'px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-ink-muted'
const TD = 'border-t border-border px-3 py-2.5'

function GroupsTable({ data, onOpen }: { data: Overview; onOpen: (id: number) => void }) {
  if (data.groups.length === 0) return <EmptyState title="Нет занятий за этот месяц" />
  return (
    <div className="card overflow-x-auto">
      <table className="w-full min-w-[820px] text-sm">
        <thead className="bg-surface-muted">
          <tr>{['Группа', 'Тренеры', 'Студ.', 'Занятий', 'Посещаемость', 'ДЗ', 'Пропуски', 'Не сдано ДЗ', 'Внимание'].map((h) => <th key={h} className={TH}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {data.groups.map((g) => (
            <tr key={g.id} className="cursor-pointer hover:bg-surface-hover" onClick={() => onOpen(g.id)}>
              <td className={TD}>
                <button type="button" className="text-left font-medium text-brand-700 hover:underline" onClick={(e) => { e.stopPropagation(); onOpen(g.id) }}>{g.name}</button>
                <p className="text-xs text-ink-muted">{g.course}</p>
              </td>
              <td className={cn(TD, 'max-w-48 truncate text-ink-secondary')}>{g.trainers.join(', ') || '—'}</td>
              <td className={TD}>{g.students}</td>
              <td className={TD}>{g.lessons}</td>
              <td className={TD}><Bar value={g.percent} /></td>
              <td className={cn(TD, 'font-medium', percentTone(g.hw_percent))}>{pct(g.hw_percent)}</td>
              <td className={cn(TD, g.absent ? 'text-danger' : '')}>{g.absent}</td>
              <td className={TD}>{g.hw_missed}</td>
              <td className={TD}>
                <span className="flex gap-1">
                  {g.warnings.critical ? <span className={cn('rounded-full px-2 py-0.5 text-xs font-semibold', LEVEL_STYLE.critical.bg, LEVEL_STYLE.critical.text)}>{g.warnings.critical}</span> : null}
                  {g.warnings.attention ? <span className={cn('rounded-full px-2 py-0.5 text-xs font-semibold', LEVEL_STYLE.attention.bg, LEVEL_STYLE.attention.text)}>{g.warnings.attention}</span> : null}
                  {!g.warnings.critical && !g.warnings.attention ? <span className="text-ink-muted">—</span> : null}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TrainersTable({ data }: { data: Overview }) {
  if (data.trainers.length === 0) return <EmptyState title="Нет данных по тренерам" />
  return (
    <div className="card overflow-x-auto">
      <table className="w-full min-w-[720px] text-sm">
        <thead className="bg-surface-muted">
          <tr>{['Тренер', 'Группы', 'Занятий', 'Посещаемость', 'ДЗ', 'Отмечено', 'Пропуски'].map((h) => <th key={h} className={TH}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {data.trainers.map((t) => (
            <tr key={t.id}>
              <td className={cn(TD, 'font-medium text-ink')}>{t.name}</td>
              <td className={cn(TD, 'max-w-56 truncate text-ink-secondary')} title={t.groups.join(', ')}>{t.groups.join(', ')}</td>
              <td className={TD}>{t.lessons}</td>
              <td className={TD}><Bar value={t.percent} /></td>
              <td className={cn(TD, percentTone(t.hw_percent))}>{pct(t.hw_percent)}</td>
              <td className={cn(TD, percentTone(t.fill_rate))} title="Доля отмеченных студентов на прошедших занятиях">{pct(t.fill_rate)}</td>
              <td className={TD}>{t.absent}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ProblemStudents({ data, onOpen }: { data: Overview; onOpen: (id: number) => void }) {
  const [query, setQuery] = useState('')
  const [level, setLevel] = useState('')
  if (data.problem_students.length === 0) return <EmptyState title="Студентов с предупреждениями нет" />
  const q = query.trim().toLowerCase()
  const rows = data.problem_students.filter((p) => (!q || p.student.name.toLowerCase().includes(q)) && (!level || p.level === level))
  return (
    <div className="space-y-3">
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <SearchInput value={query} onChange={setQuery} placeholder="Поиск студента" />
      <Select aria-label="Уровень" placeholder="Все уровни" value={level} onChange={(e) => setLevel(e.target.value)}
        options={(['critical', 'attention', 'warning'] as const).map((l) => ({ value: l, label: LEVEL_STYLE[l].label }))} />
    </div>
    <div className="card overflow-x-auto">
      <table className="w-full min-w-[720px] text-sm">
        <thead className="bg-surface-muted">
          <tr>{['Студент', 'Группа', 'Статус', 'Пропуски', 'Подряд', 'Не сдано ДЗ', 'Посещаемость', 'Причины'].map((h) => <th key={h} className={TH}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr key={`${p.group.id}-${p.student.id}`}>
              <td className={cn(TD, 'font-medium text-ink')}>{p.student.name}</td>
              <td className={TD}><button type="button" className="text-brand-700 hover:underline" onClick={() => onOpen(p.group.id)}>{p.group.name}</button></td>
              <td className={TD}><WarningDot level={p.level} title={p.warnings.map((w) => w.label).join('\n')} /></td>
              <td className={cn(TD, 'text-danger')}>{p.stats.absent}</td>
              <td className={TD}>{p.stats.consecutive_absences}</td>
              <td className={TD}>{p.stats.hw_missed}</td>
              <td className={cn(TD, percentTone(p.stats.percent))}>{pct(p.stats.percent)}</td>
              <td className={cn(TD, 'text-ink-secondary')}>{p.warnings.map((w) => w.label).join(' · ')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
    </div>
  )
}

const THRESHOLD_FIELDS: { key: keyof MatrixSettings; label: string }[] = [
  { key: 'consecutive_absences_warning', label: 'Пропусков подряд — предупреждение' },
  { key: 'monthly_absences_attention', label: 'Пропусков за месяц — обратить внимание' },
  { key: 'monthly_absences_critical', label: 'Пропусков за месяц — критично' },
  { key: 'missed_homework_warning', label: 'Несданных ДЗ — предупреждение' },
]

export function SettingsModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const { data } = useMatrixSettings()
  const save = useUpdateMatrixSettings()
  const { showToast } = useToast()
  const [form, setForm] = useState<Partial<MatrixSettings>>({})

  useEffect(() => {
    if (data && isOpen) setForm(data)
  }, [data, isOpen])

  const submit = () => {
    const payload: Partial<MatrixSettings> = {}
    for (const f of THRESHOLD_FIELDS) (payload as Record<string, unknown>)[f.key] = Number(form[f.key])
    if (data?.can_edit_permissions) {
      payload.team_lead_can_edit = !!form.team_lead_can_edit
      payload.operations_director_can_edit = !!form.operations_director_can_edit
    }
    save.mutate(payload, {
      onSuccess: () => { showToast('Настройки сохранены', 'success'); onClose() },
      onError: (error) => showToast(extractErrorMessage(error, 'Не удалось сохранить настройки'), 'error'),
    })
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Пороги предупреждений">
      {!data ? <LoadingState /> : (
        <div className="space-y-4">
          {THRESHOLD_FIELDS.map((f) => (
            <label key={f.key} className="flex items-center justify-between gap-4 text-sm">
              <span className="text-ink">{f.label}</span>
              <input type="number" min={1} max={50} className="form-control w-20" disabled={!data.can_edit_thresholds}
                value={String(form[f.key] ?? '')} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })} />
            </label>
          ))}
          {data.can_edit_permissions ? (
            <div className="space-y-2 border-t border-border pt-4">
              <p className="text-sm font-medium text-ink">Кто ещё может изменять отметки</p>
              {([['team_lead_can_edit', 'Team Lead'], ['operations_director_can_edit', 'Операционный директор']] as const).map(([key, label]) => (
                <label key={key} className="flex items-center gap-2 text-sm text-ink-secondary">
                  <input type="checkbox" className="size-4 accent-brand-500" checked={!!form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.checked })} />
                  {label}
                </label>
              ))}
              <p className="text-xs text-ink-muted">Ассистенты получают право отмечать в назначении к группе.</p>
            </div>
          ) : null}
          <div className="flex justify-end gap-2 border-t border-border pt-4">
            <Button variant="secondary" onClick={onClose}>Отменить</Button>
            {data.can_edit_thresholds ? <Button onClick={submit} isLoading={save.isPending}>Сохранить</Button> : null}
          </div>
        </div>
      )}
    </Modal>
  )
}

const ROLE_LABEL: Record<string, string> = {
  admin: 'Администратор', teacher: 'Тренер', assistant: 'Ассистент', team_lead: 'Team Lead', operations_director: 'Опер. директор',
}

function ExcusedTable({ data, onOpen }: { data: Overview; onOpen: (id: number) => void }) {
  const [onlyMissing, setOnlyMissing] = useState(false)
  if (data.excused.length === 0) return <EmptyState title="Уважительных причин за месяц нет" />
  const missing = data.excused.filter((e) => e.missing_reason).length
  const rows = onlyMissing ? data.excused.filter((e) => e.missing_reason) : data.excused
  return (
    <div className="space-y-3">
      <label className="flex items-center gap-2 text-sm text-ink-secondary">
        <input type="checkbox" className="size-4 accent-brand-500" checked={onlyMissing} onChange={(e) => setOnlyMissing(e.target.checked)} />
        Только без указанной причины ({missing})
      </label>
      <div className="card overflow-x-auto">
        <table className="w-full min-w-[720px] text-sm">
          <thead className="bg-surface-muted">
            <tr>{['Дата', 'Студент', 'Группа', 'Причина', 'Комментарий', 'Отметил'].map((h) => <th key={h} className={TH}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((e) => (
              <tr key={e.id}>
                <td className={TD}>{shortDate(e.date)}</td>
                <td className={cn(TD, 'font-medium text-ink')}>{e.student.name}</td>
                <td className={TD}><button type="button" className="text-brand-700 hover:underline" onClick={() => onOpen(e.group.id)}>{e.group.name}</button></td>
                <td className={TD}>
                  {e.missing_reason ? (
                    <span className="inline-flex items-center gap-1 text-warning"><AlertCircle className="size-4" aria-hidden />Не указана</span>
                  ) : e.reason}
                </td>
                <td className={cn(TD, 'text-ink-secondary')}>{e.comment || '—'}</td>
                <td className={cn(TD, 'text-ink-secondary')}>{e.updated_by?.name ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function AssistantsTable({ data }: { data: Overview }) {
  if (data.assistants.length === 0) {
    return <EmptyState title="Ассистенты в этом месяце отметок не меняли" description="Здесь видно, сколько отметок, ДЗ и комментариев изменил каждый ассистент." />
  }
  return (
    <div className="card overflow-x-auto">
      <table className="w-full min-w-[720px] text-sm">
        <thead className="bg-surface-muted">
          <tr>{['Ассистент', 'Группы', 'Изменений', 'Посещаемость', 'ДЗ', 'Комментарии', 'Студентов', 'Последнее'].map((h) => <th key={h} className={TH}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {data.assistants.map((a) => (
            <tr key={a.user.id}>
              <td className={cn(TD, 'font-medium text-ink')}>{a.user.name}</td>
              <td className={cn(TD, 'max-w-56 truncate text-ink-secondary')} title={a.groups.join(', ')}>{a.groups.join(', ')}</td>
              <td className={cn(TD, 'font-semibold')}>{a.changes}</td>
              <td className={TD}>{a.attendance_changes}</td>
              <td className={TD}>{a.homework_changes}</td>
              <td className={TD}>{a.comments}</td>
              <td className={TD}>{a.students}</td>
              <td className={cn(TD, 'text-ink-secondary')}>{formatDateTime(a.last_change)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Journal({ data, onOpen }: { data: Overview; onOpen: (id: number) => void }) {
  if (data.history.length === 0) return <EmptyState title="Изменений через таблицу за месяц не было" />
  return (
    <ol className="card divide-y divide-border">
      {data.history.map((h) => (
        <li key={h.id} className="flex flex-col gap-1 px-4 py-3 text-sm sm:flex-row sm:gap-4">
          <div className="shrink-0 text-xs text-ink-muted sm:w-44">
            <p>{formatDateTime(h.at)}</p>
            <p>{h.actor?.name ?? 'Система'} · {ROLE_LABEL[h.actor_role] ?? h.actor_role}</p>
          </div>
          <div className="min-w-0">
            <p className="text-ink">
              <span className="font-medium">{h.student.name}</span>
              {' · '}
              <button type="button" className="text-brand-700 hover:underline" onClick={() => onOpen(h.group.id)}>{h.group.name}</button>
              {' · занятие '}{shortDate(h.date)}
            </p>
            <ul className="text-ink-secondary">
              {h.changes.map((c) => <li key={c.field}>{c.label}: {c.before} → {c.after}</li>)}
            </ul>
          </div>
        </li>
      ))}
    </ol>
  )
}
