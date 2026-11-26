import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle2, Layers, X } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { DatePicker } from '@/components/ui/DatePicker'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { useParallelMutation, useParallelOptions, useSessionConflictCheck } from '@/hooks/useParallelLessons'
import { extractErrorMessage } from '@/lib/apiError'
import { Field, FormError, ModalActions } from '@/features/assistant/ui'
import { parallelLessonsApi } from '@/api/parallelLessons'
import type { ParallelSession, SessionInput } from '@/types/parallelLessons'

import { hm } from './shared'

/** Debounce a value so the live conflict check doesn't fire on every key. */
function useDebounced<T>(value: T, ms = 300): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), ms)
    return () => clearTimeout(timer)
  }, [value, ms])
  return debounced
}

/**
 * Create or edit a parallel session: classroom, trainer, date, time, any
 * number of groups, topic and notes. Before saving, the form shows the
 * backend's own conflict check (trainer / room / every group against
 * regular lessons and other sessions); the save repeats it under locks.
 * Editing: groups are managed on the session page; once the session has
 * started only the content can change.
 */
export function SessionFormModal({ session, onClose, onSaved }: {
  session?: ParallelSession
  onClose: () => void
  onSaved?: (session: ParallelSession) => void
}) {
  const { showToast } = useToast()
  const options = useParallelOptions()
  const editing = Boolean(session)
  const scheduleLocked = editing && !session?.capabilities.can_change_schedule

  const [form, setForm] = useState({
    room: session ? String(session.room.id) : '',
    teacher: session ? String(session.teacher.id) : '',
    subject: session?.subject ? String(session.subject.id) : '',
    date: session?.date ?? '',
    start: session ? hm(session.start_time) : '15:00',
    end: session ? hm(session.end_time) : '16:00',
    topic: session?.topic ?? '',
    description: session?.description ?? '',
    notes: session?.notes ?? '',
  })
  const [groups, setGroups] = useState<number[]>(session ? session.groups.filter((p) => p.status === 'active').map((p) => p.group.id) : [])
  const [query, setQuery] = useState('')
  const set = (patch: Partial<typeof form>) => setForm((current) => ({ ...current, ...patch }))

  const timeOk = Boolean(form.start && form.end && form.end > form.start)
  const ready = Boolean(form.room && form.teacher && form.date && timeOk && groups.length)
  const checkBody = useDebounced(useMemo(() => ({
    teacher: Number(form.teacher) || undefined, room: Number(form.room) || undefined, date: form.date,
    start_time: form.start, end_time: form.end, groups, session: session?.id,
  }), [form.teacher, form.room, form.date, form.start, form.end, groups, session?.id]))
  // Only check a complete payload — judged on the debounced body itself, so a
  // stale (still empty) body never reaches the API.
  const checkReady = Boolean(checkBody.teacher && checkBody.room && checkBody.date && checkBody.groups.length
    && checkBody.start_time && checkBody.end_time && checkBody.end_time > checkBody.start_time)
  const check = useSessionConflictCheck(checkBody, checkReady && !scheduleLocked)
  // The shown result must belong to the form as it is now.
  const current = checkBody.date === form.date && checkBody.start_time === form.start && checkBody.end_time === form.end
    && String(checkBody.teacher ?? '') === form.teacher && String(checkBody.room ?? '') === form.room && checkBody.groups === groups
  const conflicts = ready && current ? check.data?.conflicts ?? [] : []

  const save = useParallelMutation(async () => {
    const body: SessionInput = {
      room: Number(form.room), teacher: Number(form.teacher), subject: form.subject ? Number(form.subject) : null,
      date: form.date, start_time: form.start, end_time: form.end, groups,
      topic: form.topic, description: form.description, notes: form.notes,
    }
    if (session) {
      const { groups: _groups, ...changes } = body
      void _groups
      return parallelLessonsApi.update(session.id, scheduleLocked
        ? { topic: body.topic, description: body.description, notes: body.notes }
        : changes)
    }
    return parallelLessonsApi.create(body)
  })

  const groupOptions = options.data?.groups ?? []
  const byId = new Map(groupOptions.map((g) => [g.id, g]))
  const visible = groupOptions.filter((g) => !query || g.name.toLowerCase().includes(query.toLowerCase()) || g.course.toLowerCase().includes(query.toLowerCase()))
  const students = groups.reduce((sum, id) => sum + (byId.get(id)?.students_count ?? 0), 0)
  const toggle = (id: number) => setGroups((current) => current.includes(id) ? current.filter((g) => g !== id) : [...current, id])

  return (
    <Modal isOpen onClose={onClose} size="lg" title={editing ? 'Изменить параллельное занятие' : 'Новое параллельное занятие'} icon={<Layers className="size-5 text-brand-600" aria-hidden />}>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault()
          save.mutate(undefined, {
            onSuccess: (saved) => {
              showToast(editing ? 'Занятие сохранено' : 'Параллельное занятие создано', 'success')
              onSaved?.(saved)
              onClose()
            },
          })
        }}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Аудитория" htmlFor="ps-room" required>
            <Select id="ps-room" required disabled={scheduleLocked} placeholder="Выберите аудиторию" value={form.room}
              options={(options.data?.rooms ?? []).map((r) => ({ value: String(r.id), label: r.capacity ? `${r.name} · ${r.capacity} мест` : r.name }))}
              onChange={(e) => set({ room: e.target.value })} />
          </Field>
          <Field label="Тренер" htmlFor="ps-teacher" required>
            <Select id="ps-teacher" required disabled={scheduleLocked} placeholder="Выберите тренера" value={form.teacher}
              options={(options.data?.teachers ?? []).map((t) => ({ value: String(t.id), label: t.name }))}
              onChange={(e) => set({ teacher: e.target.value })} />
          </Field>
          <Field label="Дата" htmlFor="ps-date" required>
            <DatePicker id="ps-date" required disabled={scheduleLocked} value={form.date} onChange={(e) => set({ date: e.target.value })} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Начало" htmlFor="ps-start" required>
              <Input id="ps-start" type="time" required disabled={scheduleLocked} value={form.start} onChange={(e) => set({ start: e.target.value })} />
            </Field>
            <Field label="Окончание" htmlFor="ps-end" required>
              <Input id="ps-end" type="time" required disabled={scheduleLocked} value={form.end} onChange={(e) => set({ end: e.target.value })} />
            </Field>
          </div>
        </div>
        {!timeOk && form.start && form.end ? <p role="alert" className="text-sm text-danger">Время окончания должно быть позже времени начала.</p> : null}

        {!editing ? (
          <Field label={`Группы (${groups.length} выбрано · ${students} студентов)`} required
            hint="Любое количество групп. У каждой группы своё занятие — со своей посещаемостью и ДЗ.">
            <div className="space-y-2">
              {groups.length ? (
                <div className="flex flex-wrap gap-1.5" aria-label="Выбранные группы">
                  {groups.map((id) => (
                    <button key={id} type="button" onClick={() => toggle(id)}
                      className="inline-flex items-center gap-1 rounded-full bg-brand-50 px-2.5 py-1 text-xs font-medium text-brand-700 hover:bg-brand-100"
                      aria-label={`Убрать группу ${byId.get(id)?.name ?? id}`}>
                      {byId.get(id)?.name ?? id}<X className="size-3" aria-hidden />
                    </button>
                  ))}
                </div>
              ) : null}
              <SearchInput value={query} onChange={setQuery} placeholder="Найти группу или курс" />
              <ul className="max-h-48 overflow-y-auto rounded-lg border border-border" aria-label="Группы">
                {visible.map((g) => (
                  <li key={g.id}>
                    <label className="flex cursor-pointer items-center gap-2 px-3 py-2 text-sm hover:bg-surface-hover">
                      <input type="checkbox" className="size-4 accent-brand-500" checked={groups.includes(g.id)} onChange={() => toggle(g.id)} />
                      <span className="font-medium text-ink">{g.name}</span>
                      <span className="truncate text-ink-secondary">{g.course}</span>
                      <span className="ml-auto text-xs text-ink-muted">{g.students_count} студ.</span>
                    </label>
                  </li>
                ))}
                {!visible.length ? <li className="px-3 py-2 text-sm text-ink-muted">Ничего не найдено</li> : null}
              </ul>
            </div>
          </Field>
        ) : null}

        <Field label="Предмет" htmlFor="ps-subject" hint="Необязательно — по нему выбирается учебная программа группы, если их несколько.">
          <Select id="ps-subject" disabled={scheduleLocked} placeholder="Не указан" value={form.subject}
            options={(options.data?.subjects ?? []).map((s) => ({ value: String(s.id), label: s.name }))}
            onChange={(e) => set({ subject: e.target.value })} />
        </Field>
        <Field label="Тема занятия" htmlFor="ps-topic">
          <Input id="ps-topic" maxLength={255} value={form.topic} onChange={(e) => set({ topic: e.target.value })} />
        </Field>
        <Field label="Описание" htmlFor="ps-description">
          <Textarea id="ps-description" rows={2} value={form.description} onChange={(e) => set({ description: e.target.value })} />
        </Field>
        <Field label="Заметки" htmlFor="ps-notes">
          <Textarea id="ps-notes" rows={2} value={form.notes} onChange={(e) => set({ notes: e.target.value })} />
        </Field>

        {scheduleLocked ? (
          <p className="text-xs text-ink-secondary">Занятие уже началось — можно изменить только тему, описание и заметки.</p>
        ) : conflicts.length ? (
          <div role="alert" className="rounded-lg border border-danger/30 bg-danger-soft/60 px-3 py-2 text-sm">
            <p className="flex items-center gap-1.5 font-semibold text-danger"><AlertTriangle className="size-4" aria-hidden />Есть пересечения — сохранить нельзя:</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-5 text-ink">{conflicts.map((c, i) => <li key={i}>{c.message}</li>)}</ul>
          </div>
        ) : ready && current && check.data?.ok && !check.isFetching ? (
          <p className="flex items-center gap-1.5 text-sm text-brand-700"><CheckCircle2 className="size-4" aria-hidden />Тренер, аудитория и все группы свободны в это время.</p>
        ) : (
          <p className="text-xs text-ink-secondary">Тренер, аудитория и каждая группа проверяются на занятость — и обычными занятиями, и другими параллельными.</p>
        )}

        <FormError message={save.error ? extractErrorMessage(save.error) : null} />
        <ModalActions>
          <Button type="button" variant="secondary" onClick={onClose}>Отмена</Button>
          <Button type="submit" isLoading={save.isPending}
            disabled={save.isPending || (!scheduleLocked && (!ready || !current || check.isFetching || conflicts.length > 0))}>
            {editing ? 'Сохранить' : 'Создать занятие'}
          </Button>
        </ModalActions>
      </form>
    </Modal>
  )
}
