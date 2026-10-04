import { useMemo, useState } from 'react'
import { AxiosError } from 'axios'
import {
  BookOpen,
  Building2,
  CalendarDays,
  CalendarPlus,
  Clock,
  Pencil,
  Plus,
  Save,
  Trash2,
  UserRound,
} from 'lucide-react'
import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Select } from '@/components/ui/Select'
import { useToast } from '@/components/ui/Toast'
import { useAcademicConfig, useGenerateLessons, useSaveAcademicProgram } from '@/hooks/useGroups'
import { extractErrorMessage } from '@/lib/apiError'
import type { AcademicConfig, AcademicProgram } from '@/types/academy'
import { DAY_LABELS, WEEKDAY_ORDER, type DayOfWeek } from '@/types/common'

/**
 * «Расписание группы» for Admin / Team Lead (manage_group_academic_config):
 * who teaches what (program = trainer + subject), on which days, when and
 * where — every day its own slot with its own time and room. Saved through
 * the backend's existing program/slot service, which checks the trainer's,
 * the room's and the group's conflicts; lessons come from the existing
 * generator, one per slot occurrence.
 */
export function GroupAcademicConfig({ groupId }: { groupId: number }) {
  const { data, isPending, isError, refetch } = useAcademicConfig(groupId)
  const [editing, setEditing] = useState<number | 'new' | null>(null)

  if (isPending) return <LoadingState label="Загружаем расписание группы…" />
  if (isError || !data) return <ErrorState onRetry={() => void refetch()} />

  const programs = data.programs.filter((p) => p.is_active)
  const freeSubjects = data.subjects.filter((s) => !programs.some((p) => p.subject?.id === s.id))

  return (
    <section aria-label="Расписание группы" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="section-title flex items-center gap-2">
          <CalendarDays className="size-5 text-ink-muted" aria-hidden />
          Расписание группы
        </h3>
        <div className="flex flex-wrap gap-2">
          {freeSubjects.length > 0 && editing === null ? (
            <Button variant="secondary" size="sm" leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setEditing('new')}>
              Добавить предмет и тренера
            </Button>
          ) : null}
          <GenerateLessonsButton groupId={groupId} disabled={programs.every((p) => p.slots.length === 0)} />
        </div>
      </div>

      {programs.length === 0 && editing !== 'new' ? (
        <EmptyState
          icon={CalendarDays}
          title="Расписание не настроено"
          description="Назначьте тренера и предмет и добавьте дни занятий."
          action={
            <Button leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setEditing('new')}>
              Настроить расписание
            </Button>
          }
        />
      ) : null}

      {programs.map((program) =>
        editing === program.id ? (
          <ProgramEditor key={program.id} groupId={groupId} config={data} program={program} onDone={() => setEditing(null)} />
        ) : (
          <ProgramView key={program.id} program={program} onEdit={editing === null ? () => setEditing(program.id) : undefined} />
        ),
      )}

      {editing === 'new' ? (
        <ProgramEditor groupId={groupId} config={data} program={null} subjects={freeSubjects} onDone={() => setEditing(null)} />
      ) : null}
    </section>
  )
}

function ProgramView({ program, onEdit }: { program: AcademicProgram; onEdit?: () => void }) {
  return (
    <article className="card" data-testid="program-view">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-4 py-3">
        <div className="grid gap-1 text-sm sm:grid-cols-2 sm:gap-x-8">
          <p className="flex items-center gap-2">
            <UserRound className="size-4 text-ink-muted" aria-hidden />
            <span className="text-ink-secondary">Тренер:</span>
            <Link to={`/app/trainers/${program.teacher.id}`} className="font-medium text-brand-700 hover:underline">
              {program.teacher.name}
            </Link>
          </p>
          <p className="flex items-center gap-2">
            <BookOpen className="size-4 text-ink-muted" aria-hidden />
            <span className="text-ink-secondary">Предмет:</span>
            <span className="font-medium text-ink">{program.subject?.name ?? 'без предмета'}</span>
          </p>
          <p className="text-xs text-ink-muted sm:col-span-2">
            {program.assigned_by ? `Изменил: ${program.assigned_by} · ` : ''}
            {program.assigned_at ? new Date(program.assigned_at).toLocaleDateString('ru-RU') : ''}
          </p>
        </div>
        {onEdit ? (
          <Button variant="secondary" size="sm" leftIcon={<Pencil className="size-4" aria-hidden />} onClick={onEdit}>
            Изменить расписание
          </Button>
        ) : null}
      </div>
      {program.slots.length === 0 ? (
        <p className="px-4 py-3 text-sm text-ink-secondary">Дни занятий не заданы.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">День</th>
                <th scope="col">Время</th>
                <th scope="col">Кабинет</th>
                <th scope="col">Предмет</th>
                <th scope="col">Тренер</th>
              </tr>
            </thead>
            <tbody>
              {program.slots.map((slot) => (
                <tr key={slot.id}>
                  <td className="font-medium text-ink">{slot.day_label}</td>
                  <td>
                    {slot.start}–{slot.end}
                  </td>
                  <td>{slot.room?.name ?? '—'}</td>
                  <td>{program.subject?.name ?? '—'}</td>
                  <td>{program.teacher.name}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </article>
  )
}

interface Row {
  key: string
  id?: number
  day: DayOfWeek
  start: string
  end: string
  room: string
}

let rowSeq = 0
const nextKey = () => `row-${++rowSeq}`

function backendErrors(error: unknown): string[] {
  const body = error instanceof AxiosError ? error.response?.data : undefined
  if (body && typeof body === 'object' && !Array.isArray(body)) {
    const messages = Object.values(body as Record<string, unknown>).flatMap((value) =>
      Array.isArray(value) ? value.map(String) : [String(value)],
    )
    if (messages.length) return messages
  }
  return [extractErrorMessage(error, 'Не удалось сохранить расписание')]
}

function ProgramEditor({
  groupId,
  config,
  program,
  subjects,
  onDone,
}: {
  groupId: number
  config: AcademicConfig
  program: AcademicProgram | null
  subjects?: AcademicConfig['subjects']
  onDone: () => void
}) {
  const { showToast } = useToast()
  const mutation = useSaveAcademicProgram(groupId)
  const [teacher, setTeacher] = useState(program ? String(program.teacher.id) : '')
  const [subject, setSubject] = useState(program?.subject ? String(program.subject.id) : '')
  const [rows, setRows] = useState<Row[]>(() =>
    (program?.slots ?? []).map((slot) => ({
      key: nextKey(),
      id: slot.id,
      day: slot.day,
      start: slot.start,
      end: slot.end,
      room: slot.room ? String(slot.room.id) : '',
    })),
  )
  const [isAdding, setAdding] = useState(program === null)
  const [errors, setErrors] = useState<string[]>([])

  const subjectOptions = (subjects ?? config.subjects).map((s) => ({ value: String(s.id), label: s.name }))
  if (program?.subject && !subjectOptions.some((o) => o.value === String(program.subject?.id))) {
    subjectOptions.unshift({ value: String(program.subject.id), label: program.subject.name })
  }
  const roomOptions = config.rooms.map((r) => ({ value: String(r.id), label: r.name }))

  const update = (key: string, patch: Partial<Row>) => setRows((current) => current.map((r) => (r.key === key ? { ...r, ...patch } : r)))

  function validate(): string[] {
    const problems: string[] = []
    if (!teacher) problems.push('Выберите тренера.')
    if (!subject) problems.push('Выберите предмет.')
    if (rows.length === 0) problems.push('Добавьте хотя бы один день занятий.')
    for (const row of rows) {
      if (!row.start || !row.end) problems.push(`${DAY_LABELS[row.day]}: укажите время начала и окончания.`)
      else if (row.end <= row.start) problems.push(`${DAY_LABELS[row.day]}: время окончания должно быть позже времени начала.`)
    }
    return problems
  }

  async function handleSave() {
    const problems = validate()
    setErrors(problems)
    if (problems.length) return
    try {
      await mutation.mutateAsync({
        programId: program?.id ?? null,
        payload: {
          teacher: Number(teacher),
          subject: Number(subject),
          schedule: rows.map((r) => ({ ...(r.id ? { id: r.id } : {}), day: r.day, start: r.start, end: r.end, room: r.room ? Number(r.room) : null })),
        },
      })
      showToast('Расписание сохранено', 'success')
      onDone()
    } catch (error) {
      setErrors(backendErrors(error))
    }
  }

  return (
    <article className="card card-body space-y-4" data-testid="program-editor" aria-label="Изменение расписания">
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor={`teacher-${program?.id ?? 'new'}`} className="mb-1.5 flex items-center gap-2 field-label">
            <UserRound className="size-4 text-ink-muted" aria-hidden />
            Тренер *
          </label>
          <Select
            id={`teacher-${program?.id ?? 'new'}`}
            value={teacher}
            onChange={(event) => setTeacher(event.target.value)}
            placeholder="Выберите тренера"
            options={config.trainers.map((t) => ({
              value: String(t.id),
              label: t.subjects.length ? `${t.name} · ${t.subjects.join(', ')}` : t.name,
            }))}
          />
        </div>
        <div>
          <label htmlFor={`subject-${program?.id ?? 'new'}`} className="mb-1.5 flex items-center gap-2 field-label">
            <BookOpen className="size-4 text-ink-muted" aria-hidden />
            Предмет *
          </label>
          <Select
            id={`subject-${program?.id ?? 'new'}`}
            value={subject}
            onChange={(event) => setSubject(event.target.value)}
            placeholder="Выберите предмет"
            options={subjectOptions}
            disabled={Boolean(program?.has_lessons)}
          />
          {program?.has_lessons ? (
            <p className="mt-1 text-xs text-ink-muted">У программы уже есть занятия — предмет не меняется.</p>
          ) : null}
        </div>
      </div>

      <div>
        <p className="mb-2 flex items-center gap-2 field-label">
          <CalendarDays className="size-4 text-ink-muted" aria-hidden />
          Дни занятий *
        </p>
        {rows.length === 0 ? <p className="text-sm text-ink-secondary">Дни ещё не добавлены.</p> : null}
        <ul className="space-y-2">
          {rows.map((row) => (
            <li key={row.key} className="grid grid-cols-2 items-end gap-2 sm:grid-cols-[1.2fr_1fr_1fr_1.4fr_auto]" data-testid="slot-row">
              <Select
                aria-label="День"
                value={row.day}
                onChange={(event) => update(row.key, { day: event.target.value as DayOfWeek })}
                options={config.weekdays.map((d) => ({ value: d.code, label: d.label }))}
              />
              <Input aria-label="Начало" type="time" value={row.start} onChange={(event) => update(row.key, { start: event.target.value })} />
              <Input aria-label="Окончание" type="time" value={row.end} onChange={(event) => update(row.key, { end: event.target.value })} />
              <Select
                aria-label="Кабинет"
                value={row.room}
                onChange={(event) => update(row.key, { room: event.target.value })}
                placeholder="Без кабинета"
                options={roomOptions}
              />
              <Button
                variant="ghost"
                size="sm"
                aria-label={`Удалить ${DAY_LABELS[row.day]} ${row.start}`}
                onClick={() => setRows((current) => current.filter((r) => r.key !== row.key))}
              >
                <Trash2 className="size-4" aria-hidden />
              </Button>
            </li>
          ))}
        </ul>

        {isAdding ? (
          <AddDaysPanel
            roomOptions={roomOptions}
            onAdd={(added) => {
              setRows((current) => [...current, ...added])
              setAdding(false)
            }}
            onCancel={() => setAdding(false)}
          />
        ) : (
          <Button className="mt-2" variant="secondary" size="sm" leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setAdding(true)}>
            Добавить день
          </Button>
        )}
      </div>

      {errors.length ? (
        <ul role="alert" className="space-y-1 rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">
          {errors.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      ) : null}

      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onDone} disabled={mutation.isPending}>
          Отмена
        </Button>
        <Button leftIcon={<Save className="size-4" aria-hidden />} onClick={() => void handleSave()} isLoading={mutation.isPending}>
          Сохранить
        </Button>
      </div>
    </article>
  )
}

/** «Добавить день»: one or several weekdays with the same time and room at
 * once (each becomes its own slot — edit any of them separately after). */
function AddDaysPanel({
  roomOptions,
  onAdd,
  onCancel,
}: {
  roomOptions: { value: string; label: string }[]
  onAdd: (rows: Row[]) => void
  onCancel: () => void
}) {
  const [days, setDays] = useState<DayOfWeek[]>([])
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [room, setRoom] = useState('')
  const [error, setError] = useState<string | null>(null)
  const ordered = useMemo(() => WEEKDAY_ORDER.filter((d) => days.includes(d)), [days])

  function add() {
    if (!ordered.length) return setError('Выберите хотя бы один день.')
    if (!start || !end) return setError('Укажите время начала и окончания.')
    if (end <= start) return setError('Время окончания должно быть позже времени начала.')
    onAdd(ordered.map((day) => ({ key: nextKey(), day, start, end, room })))
  }

  return (
    <div className="mt-3 space-y-3 rounded-lg border border-border p-3" data-testid="add-days">
      <fieldset>
        <legend className="mb-2 text-sm font-medium text-ink">Дни</legend>
        <div className="flex flex-wrap gap-2">
          {WEEKDAY_ORDER.map((day) => (
            <label key={day} className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-sm">
              <input
                type="checkbox"
                checked={days.includes(day)}
                onChange={(event) => setDays((current) => (event.target.checked ? [...current, day] : current.filter((d) => d !== day)))}
              />
              {DAY_LABELS[day]}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="grid gap-2 sm:grid-cols-3">
        <label className="text-sm">
          <span className="mb-1 flex items-center gap-1.5 text-ink-secondary">
            <Clock className="size-4" aria-hidden />
            Начало
          </span>
          <Input type="time" value={start} onChange={(event) => setStart(event.target.value)} aria-label="Начало новых дней" />
        </label>
        <label className="text-sm">
          <span className="mb-1 flex items-center gap-1.5 text-ink-secondary">
            <Clock className="size-4" aria-hidden />
            Окончание
          </span>
          <Input type="time" value={end} onChange={(event) => setEnd(event.target.value)} aria-label="Окончание новых дней" />
        </label>
        <label className="text-sm">
          <span className="mb-1 flex items-center gap-1.5 text-ink-secondary">
            <Building2 className="size-4" aria-hidden />
            Кабинет
          </span>
          <Select value={room} onChange={(event) => setRoom(event.target.value)} placeholder="Без кабинета" options={roomOptions} aria-label="Кабинет новых дней" />
        </label>
      </div>
      {error ? <p className="text-sm text-danger">{error}</p> : null}
      <div className="flex justify-end gap-2">
        <Button variant="secondary" size="sm" onClick={onCancel}>
          Отмена
        </Button>
        <Button size="sm" leftIcon={<Plus className="size-4" aria-hidden />} onClick={add}>
          Добавить
        </Button>
      </div>
    </div>
  )
}

function GenerateLessonsButton({ groupId, disabled }: { groupId: number; disabled: boolean }) {
  const { showToast } = useToast()
  const mutation = useGenerateLessons(groupId)
  const [warnings, setWarnings] = useState<string[]>([])

  async function generate() {
    try {
      const result = await mutation.mutateAsync()
      setWarnings(result.warnings)
      showToast(
        result.created_count
          ? `Создано занятий: ${result.created_count}${result.first_date ? ` (с ${new Date(result.first_date).toLocaleDateString('ru-RU')})` : ''}`
          : 'Новых занятий нет — расписание уже сгенерировано',
        'success',
      )
    } catch (error) {
      showToast(extractErrorMessage(error, 'Не удалось сгенерировать занятия'), 'error')
    }
  }

  return (
    <>
      <Button size="sm" leftIcon={<CalendarPlus className="size-4" aria-hidden />} onClick={() => void generate()} isLoading={mutation.isPending} disabled={disabled}>
        Сгенерировать занятия
      </Button>
      {warnings.length ? (
        <ul className="w-full space-y-1 rounded-lg bg-warning-soft px-3 py-2 text-xs text-warning">
          {warnings.slice(0, 5).map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      ) : null}
    </>
  )
}

/** Compact read view for «Общая информация»: trainer, subject, days, time. */
export function AcademicConfigSummary({ groupId, onEdit }: { groupId: number; onEdit: () => void }) {
  const { data } = useAcademicConfig(groupId)
  if (!data) return null
  const programs = data.programs.filter((p) => p.is_active)
  return (
    <section className="card card-body space-y-3" aria-label="Учебная конфигурация">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="section-title">Учебная конфигурация</h3>
        <Button variant="secondary" size="sm" leftIcon={<Pencil className="size-4" aria-hidden />} onClick={onEdit}>
          Изменить расписание
        </Button>
      </div>
      {programs.length === 0 ? <p className="text-sm text-ink-secondary">Тренер и расписание не назначены.</p> : null}
      {programs.map((program) => (
        <dl key={program.id} className="grid gap-2 text-sm sm:grid-cols-4" data-testid="config-summary">
          <Item icon={UserRound} label="Тренер" value={program.teacher.name} />
          <Item icon={BookOpen} label="Предмет" value={program.subject?.name ?? '—'} />
          <Item icon={CalendarDays} label="Дни занятий" value={program.slots.map((s) => DAY_LABELS[s.day]).join(' ') || '—'} />
          <Item
            icon={Clock}
            label="Время"
            value={[...new Set(program.slots.map((s) => `${s.start}–${s.end}`))].join(', ') || '—'}
          />
        </dl>
      ))}
    </section>
  )
}

function Item({ icon: Icon, label, value }: { icon: typeof UserRound; label: string; value: string }) {
  return (
    <div>
      <dt className="flex items-center gap-1.5 text-ink-secondary">
        <Icon className="size-4 text-ink-muted" aria-hidden />
        {label}
      </dt>
      <dd className="mt-0.5 font-medium text-ink">{value}</dd>
    </div>
  )
}
