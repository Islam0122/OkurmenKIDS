import { useEffect, useMemo, useState } from 'react'
import { format, parseISO } from 'date-fns'
import { ru } from 'date-fns/locale'
import { CheckCircle2, CirclePlay, Pencil, Plus, Trash2, XCircle } from 'lucide-react'
import { useParams } from 'react-router-dom'

import { parallelLessonsApi } from '@/api/parallelLessons'
import { PageHeader } from '@/components/layout/PageHeader'
import { BackLink } from '@/components/ui/BackLink'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { DatePicker } from '@/components/ui/DatePicker'
import { ErrorState } from '@/components/ui/ErrorState'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { Tabs } from '@/components/ui/Tabs'
import { useToast } from '@/components/ui/Toast'
import {
  useParallelMutation,
  useParallelOptions,
  useParallelSession,
  useSessionHistory,
  useSessionHomework,
  useSessionRoster,
  useSessionStatistics,
} from '@/hooks/useParallelLessons'
import { extractErrorMessage } from '@/lib/apiError'
import { Field, FormError, ModalActions } from '@/features/assistant/ui'
import { TrainerDot } from '@/features/scheduleBoard/LessonCard'
import type { AttendanceMark, ParallelSession, RosterGroup } from '@/types/parallelLessons'
import { cn } from '@/utils/cn'

import { SessionFormModal } from './SessionFormModal'
import { formatDay, hm, MARK_LABELS, SessionStatusBadge, useParallelBase } from './shared'

type Section = 'attendance' | 'homework' | 'statistics' | 'groups' | 'history'

/** One parallel session: the shared data, its groups and — per group — the
 * students, their attendance, homework and statistics. What the user may do
 * comes from the backend (`capabilities`). */
export function SessionDetailPage() {
  const id = Number(useParams().id)
  const base = useParallelBase()
  const { showToast } = useToast()
  const session = useParallelSession(id)
  const [section, setSection] = useState<Section>('attendance')
  const [editing, setEditing] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [reason, setReason] = useState('')

  const start = useParallelMutation(() => parallelLessonsApi.start(id))
  const complete = useParallelMutation(() => parallelLessonsApi.complete(id))
  const cancel = useParallelMutation(() => parallelLessonsApi.cancel(id, reason))
  const actionError = start.error ?? complete.error

  if (session.isLoading) return <LoadingState label="Загрузка занятия…" />
  if (session.isError || !session.data) return <ErrorState message={extractErrorMessage(session.error)} onRetry={() => void session.refetch()} />
  const s = session.data
  const can = s.capabilities

  return (
    <div className="space-y-6">
      <BackLink to={base}>Параллельные занятия</BackLink>
      <PageHeader
        title={s.topic || `Параллельное занятие №${s.id}`}
        badge={<SessionStatusBadge status={s.status} label={s.status_display} />}
        description={`${formatDay(s.date)} · ${hm(s.start_time)}–${hm(s.end_time)} · ${s.room.name} · ${s.groups_count} групп, ${s.students_count} студентов`}
        actions={
          <div className="flex flex-wrap gap-2">
            {can.can_edit ? <Button variant="secondary" leftIcon={<Pencil className="size-4" aria-hidden />} onClick={() => setEditing(true)}>Изменить</Button> : null}
            {can.can_cancel ? <Button variant="danger" leftIcon={<XCircle className="size-4" aria-hidden />} onClick={() => setCancelling(true)}>Отменить</Button> : null}
            {can.can_start ? (
              <Button variant="secondary" leftIcon={<CirclePlay className="size-4" aria-hidden />} isLoading={start.isPending}
                onClick={() => start.mutate(undefined, { onSuccess: () => showToast('Занятие начато', 'success') })}>Начать</Button>
            ) : null}
            {can.can_complete ? (
              <Button leftIcon={<CheckCircle2 className="size-4" aria-hidden />} isLoading={complete.isPending}
                onClick={() => complete.mutate(undefined, { onSuccess: () => showToast('Занятие проведено во всех группах', 'success') })}>Завершить</Button>
            ) : null}
          </div>
        }
      />
      <FormError message={actionError ? extractErrorMessage(actionError) : null} />

      <SessionInfo session={s} />

      <Tabs
        aria-label="Разделы занятия"
        value={section}
        onChange={setSection}
        items={[
          { key: 'attendance', label: 'Студенты и посещаемость' },
          { key: 'homework', label: 'Домашнее задание' },
          { key: 'statistics', label: 'Статистика' },
          { key: 'groups', label: 'Группы' },
          { key: 'history', label: 'История' },
        ]}
      />
      {section === 'attendance' ? <AttendanceSection session={s} /> : null}
      {section === 'homework' ? <HomeworkSection session={s} /> : null}
      {section === 'statistics' ? <StatisticsSection id={s.id} /> : null}
      {section === 'groups' ? <GroupsSection session={s} /> : null}
      {section === 'history' ? <HistorySection id={s.id} /> : null}

      {editing ? <SessionFormModal session={s} onClose={() => setEditing(false)} /> : null}
      {cancelling ? (
        <Modal isOpen onClose={() => setCancelling(false)} title="Отменить параллельное занятие">
          <form className="space-y-4" onSubmit={(e) => {
            e.preventDefault()
            cancel.mutate(undefined, { onSuccess: () => { showToast('Занятие отменено', 'success'); setCancelling(false) } })
          }}>
            <p className="text-sm text-ink-secondary">Будут отменены занятия всех групп. Посещаемость и ДЗ, если они уже есть, сохранятся в истории.</p>
            <Field label="Причина" htmlFor="ps-cancel-reason"><Input id="ps-cancel-reason" maxLength={255} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
            <FormError message={cancel.error ? extractErrorMessage(cancel.error) : null} />
            <ModalActions>
              <Button type="button" variant="secondary" onClick={() => setCancelling(false)}>Назад</Button>
              <Button type="submit" variant="danger" isLoading={cancel.isPending}>Отменить занятие</Button>
            </ModalActions>
          </form>
        </Modal>
      ) : null}
    </div>
  )
}

function SessionInfo({ session: s }: { session: ParallelSession }) {
  const materials = [s.youtube_url, ...s.presentation_urls].filter(Boolean)
  return (
    <Card>
      <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div><dt className="field-label">Тренер</dt><dd className="flex items-center gap-1.5 font-medium text-ink"><TrainerDot color={s.teacher.color} />{s.teacher.name}</dd></div>
        <div><dt className="field-label">Аудитория</dt><dd className="font-medium text-ink">{s.room.name}</dd></div>
        <div><dt className="field-label">Предмет</dt><dd className="font-medium text-ink">{s.subject?.name ?? '—'}</dd></div>
        <div><dt className="field-label">Создал</dt><dd className="font-medium text-ink">{s.created_by_name ?? '—'}</dd></div>
        <div className="sm:col-span-2 lg:col-span-4">
          <dt className="field-label">Группы</dt>
          <dd className="mt-1 flex flex-wrap gap-1.5">
            {s.groups.filter((p) => p.status === 'active').map((p) => <Badge key={p.id}>{p.group.name} · {p.students_count}</Badge>)}
          </dd>
        </div>
        {s.description ? <div className="sm:col-span-2"><dt className="field-label">Описание</dt><dd className="whitespace-pre-line text-ink">{s.description}</dd></div> : null}
        {s.notes ? <div className="sm:col-span-2"><dt className="field-label">Заметки</dt><dd className="whitespace-pre-line text-ink">{s.notes}</dd></div> : null}
        {materials.length ? (
          <div className="sm:col-span-2 lg:col-span-4"><dt className="field-label">Материалы</dt>
            <dd className="flex flex-col gap-0.5">{materials.map((url) => <a key={url} href={url} target="_blank" rel="noreferrer" className="truncate text-brand-700 hover:underline">{url}</a>)}</dd>
          </div>
        ) : null}
        {s.status === 'cancelled' && s.cancellation_reason ? <div className="sm:col-span-2"><dt className="field-label">Причина отмены</dt><dd className="text-ink">{s.cancellation_reason}</dd></div> : null}
        {s.completed_at ? <div><dt className="field-label">Проведено</dt><dd className="text-ink">{format(parseISO(s.completed_at), 'd MMM HH:mm', { locale: ru })}{s.completed_by_name ? ` · ${s.completed_by_name}` : ''}</dd></div> : null}
      </dl>
    </Card>
  )
}

const MARKS: AttendanceMark[] = ['present', 'late', 'absent', 'excused']
const MARK_STYLE: Record<AttendanceMark, string> = {
  present: 'bg-brand-500 text-white',
  late: 'bg-warning text-white',
  absent: 'bg-danger text-white',
  excused: 'bg-info text-white',
}

/** Students grouped by their own group; each group is marked and saved on
 * its own lesson — students of different groups are never mixed. */
function AttendanceSection({ session }: { session: ParallelSession }) {
  const roster = useSessionRoster(session.id)
  const [groupId, setGroupId] = useState<number | null>(null)
  const groups = roster.data ?? []
  const current = groups.find((g) => g.group.id === groupId) ?? groups[0]
  if (roster.isLoading) return <LoadingState label="Загрузка студентов…" />
  if (roster.isError) return <ErrorState message={extractErrorMessage(roster.error)} onRetry={() => void roster.refetch()} />
  if (!current) return <p className="text-sm text-ink-muted">В занятии нет групп.</p>
  return (
    <div className="grid gap-4 lg:grid-cols-[14rem_1fr]">
      <nav aria-label="Группы занятия" className="flex gap-2 overflow-x-auto lg:flex-col">
        {groups.map((g) => {
          const marked = g.students.filter((st) => st.status).length
          return (
            <button key={g.group.id} type="button" onClick={() => setGroupId(g.group.id)}
              className={cn('flex shrink-0 items-center justify-between gap-3 rounded-lg border px-3 py-2 text-left text-sm',
                g.group.id === current.group.id ? 'border-brand-300 bg-brand-50 text-brand-700' : 'border-border bg-surface hover:bg-surface-hover')}>
              <span className="font-medium">{g.group.name}</span>
              <span className="text-xs tabular-nums text-ink-muted">{marked}/{g.students.length}</span>
            </button>
          )
        })}
      </nav>
      <GroupAttendance key={current.group.id} session={session} group={current} />
    </div>
  )
}

function GroupAttendance({ session, group }: { session: ParallelSession; group: RosterGroup }) {
  const { showToast } = useToast()
  const initial = useMemo(() => Object.fromEntries(group.students.map((st) => [st.student, st.status])) as Record<number, AttendanceMark | null>, [group])
  const [marks, setMarks] = useState(initial)
  useEffect(() => setMarks(initial), [initial])
  const editable = session.capabilities.can_mark_attendance
  const save = useParallelMutation(() => parallelLessonsApi.markAttendance(session.id, group.group.id,
    group.students.filter((st) => marks[st.student]).map((st) => ({ student: st.student, status: marks[st.student] as AttendanceMark }))))
  const dirty = group.students.some((st) => marks[st.student] !== st.status)
  const all = group.students.every((st) => marks[st.student])

  return (
    <Card title={group.group.name} description={`${group.students.length} студентов · посещаемость сохраняется в занятии этой группы`}
      actions={editable ? <Button size="sm" variant="ghost" onClick={() => setMarks(Object.fromEntries(group.students.map((st) => [st.student, 'present'])))}>Все присутствуют</Button> : null}>
      {group.students.length ? (
        <ul className="divide-y divide-border">
          {group.students.map((st) => (
            <li key={st.student} className="flex flex-col gap-2 py-2 sm:flex-row sm:items-center sm:justify-between">
              <span className="text-sm font-medium text-ink">{st.student_name}</span>
              <div className="flex flex-wrap gap-1" role="radiogroup" aria-label={`Отметка: ${st.student_name}`}>
                {MARKS.map((mark) => (
                  <button key={mark} type="button" role="radio" aria-checked={marks[st.student] === mark} disabled={!editable}
                    onClick={() => setMarks((m) => ({ ...m, [st.student]: mark }))}
                    className={cn('rounded-md border px-2 py-1 text-xs font-medium transition disabled:cursor-default',
                      marks[st.student] === mark ? MARK_STYLE[mark] + ' border-transparent' : 'border-border bg-surface text-ink-secondary hover:bg-surface-hover')}>
                    {MARK_LABELS[mark]}
                  </button>
                ))}
              </div>
            </li>
          ))}
        </ul>
      ) : <p className="text-sm text-ink-muted">В группе нет активных студентов.</p>}
      {editable ? (
        <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-end">
          <FormError message={save.error ? extractErrorMessage(save.error) : null} />
          {!all ? <span className="text-xs text-ink-muted">Для завершения занятия нужно отметить всех студентов.</span> : null}
          <Button disabled={!dirty || save.isPending} isLoading={save.isPending}
            onClick={() => save.mutate(undefined, { onSuccess: () => showToast(`Посещаемость «${group.group.name}» сохранена`, 'success') })}>Сохранить</Button>
        </div>
      ) : null}
    </Card>
  )
}

function HomeworkSection({ session }: { session: ParallelSession }) {
  const { showToast } = useToast()
  const homework = useSessionHomework(session.id)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [deadline, setDeadline] = useState('')
  const [only, setOnly] = useState<number[]>([])
  const active = session.groups.filter((p) => p.status === 'active')
  const add = useParallelMutation(() => parallelLessonsApi.addHomework(session.id, { title, description, deadline: deadline || null, groups: only }))

  return (
    <div className="space-y-4">
      {session.capabilities.can_add_homework ? (
        <Card title="Добавить домашнее задание" description="Общее для всех групп или только для выбранных. Создаётся обычным ДЗ в занятии каждой группы.">
          <form className="space-y-3" onSubmit={(e) => {
            e.preventDefault()
            add.mutate(undefined, { onSuccess: () => { showToast('Домашнее задание добавлено', 'success'); setTitle(''); setDescription(''); setDeadline(''); setOnly([]) } })
          }}>
            <div className="grid gap-3 sm:grid-cols-[1fr_12rem]">
              <Field label="Название" htmlFor="ps-hw-title" required><Input id="ps-hw-title" required maxLength={255} value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
              <Field label="Срок сдачи" htmlFor="ps-hw-deadline"><DatePicker id="ps-hw-deadline" value={deadline} onChange={(e) => setDeadline(e.target.value)} /></Field>
            </div>
            <Field label="Описание" htmlFor="ps-hw-description"><Input id="ps-hw-description" value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
            <fieldset>
              <legend className="mb-1.5 text-sm font-medium text-ink">Группы <span className="font-normal text-ink-secondary">(ничего не выбрано — всем)</span></legend>
              <div className="flex flex-wrap gap-3">
                {active.map((p) => (
                  <label key={p.group.id} className="flex items-center gap-1.5 text-sm">
                    <input type="checkbox" className="size-4 accent-brand-500" checked={only.includes(p.group.id)}
                      onChange={() => setOnly((o) => o.includes(p.group.id) ? o.filter((x) => x !== p.group.id) : [...o, p.group.id])} />
                    {p.group.name}
                  </label>
                ))}
              </div>
            </fieldset>
            <FormError message={add.error ? extractErrorMessage(add.error) : null} />
            <div className="flex justify-end"><Button type="submit" leftIcon={<Plus className="size-4" aria-hidden />} isLoading={add.isPending} disabled={!title.trim()}>Добавить</Button></div>
          </form>
        </Card>
      ) : null}
      <Card title="Домашние задания" padding="none">
        {homework.isLoading ? <LoadingState /> : !homework.data?.length ? <p className="px-4 py-3 text-sm text-ink-muted">Заданий пока нет.</p> : (
          <ul className="divide-y divide-border">
            {homework.data.map((hw) => (
              <li key={hw.id} className="flex flex-col gap-0.5 px-4 py-3 sm:flex-row sm:items-center sm:gap-3">
                <Badge>{hw.group_name}</Badge>
                <span className="font-medium text-ink">{hw.title}</span>
                {hw.description ? <span className="truncate text-sm text-ink-secondary">{hw.description}</span> : null}
                {hw.deadline ? <span className="text-xs text-ink-muted sm:ml-auto">до {format(parseISO(hw.deadline), 'd MMM', { locale: ru })}</span> : null}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}

function StatisticsSection({ id }: { id: number }) {
  const stats = useSessionStatistics(id)
  if (stats.isLoading) return <LoadingState />
  if (!stats.data) return <ErrorState message={extractErrorMessage(stats.error)} />
  const rate = (value: number | null) => (value === null ? '—' : `${value}%`)
  const rows = [...stats.data.groups.map((g) => ({ key: String(g.group.id), name: g.group.name, ...g })),
    { key: 'total', name: 'Итого', ...stats.data.totals, homework: null as number | null }]
  return (
    <Card padding="none">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead><tr className="border-b border-border text-left text-ink-secondary">
            {['Группа', 'Студентов', 'Отмечено', 'Присутств.', 'Опоздали', 'Отсутств.', 'Уваж.', 'Посещаемость', 'ДЗ'].map((h) => <th key={h} className="px-4 py-2 font-medium">{h}</th>)}
          </tr></thead>
          <tbody className="divide-y divide-border">
            {rows.map((row) => (
              <tr key={row.key} className={row.key === 'total' ? 'font-semibold' : undefined}>
                <td className="px-4 py-2 text-ink">{row.name}</td>
                <td className="px-4 py-2 tabular-nums">{row.students}</td>
                <td className="px-4 py-2 tabular-nums">{row.marked}</td>
                <td className="px-4 py-2 tabular-nums">{row.present}</td>
                <td className="px-4 py-2 tabular-nums">{row.late}</td>
                <td className="px-4 py-2 tabular-nums">{row.absent}</td>
                <td className="px-4 py-2 tabular-nums">{row.excused}</td>
                <td className="px-4 py-2 tabular-nums">{rate(row.attendance_rate)}</td>
                <td className="px-4 py-2 tabular-nums">{row.homework ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function GroupsSection({ session }: { session: ParallelSession }) {
  const { showToast } = useToast()
  const options = useParallelOptions(session.capabilities.can_manage_groups)
  const [adding, setAdding] = useState('')
  const [removing, setRemoving] = useState<{ id: number; name: string } | null>(null)
  const [reason, setReason] = useState('')
  const add = useParallelMutation(() => parallelLessonsApi.addGroup(session.id, Number(adding)))
  const remove = useParallelMutation(() => parallelLessonsApi.removeGroup(session.id, removing!.id, reason))
  const activeIds = new Set(session.groups.filter((p) => p.status === 'active').map((p) => p.group.id))
  const addable = (options.data?.groups ?? []).filter((g) => !activeIds.has(g.id))

  return (
    <div className="space-y-4">
      {session.capabilities.can_manage_groups ? (
        <Card title="Добавить группу" description="Группа проверяется на занятость в это время.">
          <form className="flex flex-col gap-2 sm:flex-row" onSubmit={(e) => {
            e.preventDefault()
            add.mutate(undefined, { onSuccess: () => { showToast('Группа добавлена', 'success'); setAdding('') } })
          }}>
            <Select aria-label="Группа" placeholder="Выберите группу" value={adding} options={addable.map((g) => ({ value: String(g.id), label: `${g.name} · ${g.students_count} студ.` }))}
              onChange={(e) => setAdding(e.target.value)} />
            <Button type="submit" leftIcon={<Plus className="size-4" aria-hidden />} disabled={!adding} isLoading={add.isPending}>Добавить</Button>
          </form>
          <div className="mt-2"><FormError message={add.error ? extractErrorMessage(add.error) : null} /></div>
        </Card>
      ) : null}
      <Card padding="none" title={<span className="px-4">Участие групп</span>}>
        <ul className="divide-y divide-border">
          {session.groups.map((p) => (
            <li key={p.id} className={cn('flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-center sm:gap-3', p.status === 'removed' && 'opacity-70')}>
              <span className="font-medium text-ink">{p.group.name}</span>
              <span className="text-sm text-ink-secondary">{p.students_count} студ.{p.program?.subject ? ` · ${p.program.subject}` : ''}</span>
              <Badge tone={p.status === 'active' ? 'success' : 'muted'}>{p.status_display}</Badge>
              {p.status === 'removed' && p.removal_reason ? <span className="text-xs text-ink-muted">{p.removal_reason}</span> : null}
              {p.status === 'active' && session.capabilities.can_manage_groups && activeIds.size > 1 ? (
                <Button size="sm" variant="ghost" className="sm:ml-auto" leftIcon={<Trash2 className="size-4" aria-hidden />}
                  onClick={() => { setReason(''); setRemoving({ id: p.group.id, name: p.group.name }) }}>Исключить</Button>
              ) : null}
            </li>
          ))}
        </ul>
      </Card>
      {removing ? (
        <Modal isOpen onClose={() => setRemoving(null)} title={`Исключить группу «${removing.name}»`}>
          <form className="space-y-4" onSubmit={(e) => {
            e.preventDefault()
            remove.mutate(undefined, { onSuccess: () => { showToast('Группа исключена', 'success'); setRemoving(null) } })
          }}>
            <p className="text-sm text-ink-secondary">Занятие группы будет отменено, но её посещаемость и история останутся.</p>
            <Field label="Причина" htmlFor="ps-remove-reason"><Input id="ps-remove-reason" maxLength={255} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
            <FormError message={remove.error ? extractErrorMessage(remove.error) : null} />
            <ModalActions>
              <Button type="button" variant="secondary" onClick={() => setRemoving(null)}>Назад</Button>
              <Button type="submit" variant="danger" isLoading={remove.isPending}>Исключить</Button>
            </ModalActions>
          </form>
        </Modal>
      ) : null}
    </div>
  )
}

function HistorySection({ id }: { id: number }) {
  const history = useSessionHistory(id)
  if (history.isLoading) return <LoadingState />
  return (
    <Card padding="none">
      {!history.data?.length ? <p className="px-4 py-3 text-sm text-ink-muted">История пуста.</p> : (
        <ol className="divide-y divide-border">
          {history.data.map((entry, index) => (
            <li key={index} className="flex flex-col gap-0.5 px-4 py-3 sm:flex-row sm:gap-3">
              <span className="shrink-0 text-xs tabular-nums text-ink-muted">{format(parseISO(entry.at), 'd MMM yyyy, HH:mm', { locale: ru })}</span>
              <span className="text-sm text-ink">{entry.message}</span>
              {entry.user ? <span className="text-xs text-ink-secondary sm:ml-auto">{entry.user}</span> : null}
            </li>
          ))}
        </ol>
      )}
    </Card>
  )
}

