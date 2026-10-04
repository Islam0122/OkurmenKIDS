import { useState } from 'react'
import type { FormEvent } from 'react'
import { ListTodo, NotebookPen, Save } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { DatePicker } from '@/components/ui/DatePicker'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { useSaveEntry } from '@/hooks/useWorklog'
import { extractErrorMessage } from '@/lib/apiError'
import type { EntryKind, WorkLogEntry, WorkLogEntryInput, WorklogOptions } from '@/types/worklog'

import { Field, fieldErrors, idOrNull, orNull, today } from './formUi'

const TEXT_FIELDS = [
  'with_whom',
  'title',
  'goal',
  'description',
  'result',
  'problem',
  'decision',
  'next_action',
  'responsible',
  'comment',
] as const

type FormState = Record<(typeof TEXT_FIELDS)[number], string> & {
  date: string
  time_from: string
  time_to: string
  work_type: string
  group: string
  teacher: string
  student: string
  deadline: string
  priority: string
  status: string
}

function initialState(entry: WorkLogEntry | undefined, defaults: WorkLogEntryInput | undefined): FormState {
  const source = { ...defaults, ...entry }
  const text = (value: unknown) => (value == null ? '' : String(value))
  const state = {
    date: source.date ?? today(),
    time_from: text(source.time_from).slice(0, 5),
    time_to: text(source.time_to).slice(0, 5),
    work_type: source.work_type ?? (source.entry_kind === 'task' ? 'other' : 'lesson_control'),
    group: text(source.group),
    teacher: text(source.teacher),
    student: text(source.student),
    deadline: text(source.deadline),
    priority: source.priority ?? 'medium',
    status: source.status && source.status !== 'overdue' ? source.status : 'new',
  } as FormState
  for (const key of TEXT_FIELDS) state[key] = text(source[key])
  return state
}

export interface EntryModalProps {
  isOpen: boolean
  onClose: () => void
  options: WorklogOptions
  kind: EntryKind
  entry?: WorkLogEntry
  /** Prefill for a new record, e.g. `{report: id}` for a meeting decision. */
  defaults?: WorkLogEntryInput
  title?: string
}

/**
 * A «Рабочий журнал» record or a task. A record answers the five questions
 * of section 6.13 (что сделал, когда, с кем, результат, что дальше) — the
 * backend refuses one that doesn't; a task needs an owner and a deadline.
 */
export function EntryModal({ isOpen, onClose, options, kind, entry, defaults, title }: EntryModalProps) {
  const isTask = kind === 'task'
  const [form, setForm] = useState<FormState>(() => initialState(entry, { entry_kind: kind, ...defaults }))
  const save = useSaveEntry()
  const { showToast } = useToast()
  const errors = fieldErrors(save.error)

  const set = (key: keyof FormState) => (event: { target: { value: string } }) =>
    setForm((prev) => ({ ...prev, [key]: event.target.value }))

  const students = options.students.filter((s) => !form.group || s.group === Number(form.group))

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    const payload: WorkLogEntryInput = {
      entry_kind: kind,
      date: form.date,
      time_from: orNull(form.time_from),
      time_to: orNull(form.time_to),
      work_type: form.work_type as WorkLogEntryInput['work_type'],
      group: idOrNull(form.group),
      teacher: idOrNull(form.teacher),
      student: idOrNull(form.student),
      deadline: orNull(form.deadline),
      priority: form.priority as WorkLogEntryInput['priority'],
      status: form.status as WorkLogEntryInput['status'],
      ...(defaults?.report !== undefined && !entry ? { report: defaults.report } : {}),
    }
    for (const key of TEXT_FIELDS) payload[key] = form[key].trim()
    save.mutate(
      { id: entry?.id, payload },
      {
        onSuccess: () => {
          showToast(isTask ? 'Задача сохранена' : 'Запись сохранена', 'success')
          onClose()
        },
      },
    )
  }

  const id = (name: string) => `entry-${name}`
  const statusOptions = options.statuses.filter((s) => s.value !== 'overdue')
  const shown = new Set<string>([...TEXT_FIELDS, 'date', 'time_from', 'time_to', 'work_type', 'group', 'teacher', 'student', 'deadline', 'priority', 'status'])
  const generalError =
    save.error && !Object.keys(errors).some((key) => shown.has(key)) ? extractErrorMessage(save.error) : null

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      size="lg"
      title={title ?? (entry ? (isTask ? 'Задача' : 'Запись журнала') : isTask ? 'Новая задача' : 'Новая запись')}
      icon={isTask ? <ListTodo className="size-5" aria-hidden /> : <NotebookPen className="size-5" aria-hidden />}
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        {!isTask ? (
          <p className="rounded-lg bg-surface-hover px-3 py-2 text-sm text-ink-secondary">
            Запись отвечает на пять вопросов: что сделано, когда, с кем или с какой группой, какой результат, что
            дальше.
          </p>
        ) : null}

        {isTask ? (
          <Field label="Задача" htmlFor={id('title')} error={errors.title} required>
            <Input id={id('title')} value={form.title} onChange={set('title')} placeholder="Проверить журнал группы" />
          </Field>
        ) : null}

        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Дата" htmlFor={id('date')} error={errors.date} required>
            <DatePicker id={id('date')} value={form.date} onChange={set('date')} />
          </Field>
          {!isTask ? (
            <>
              <Field label="Время с" htmlFor={id('time_from')} error={errors.time_from}>
                <Input id={id('time_from')} type="time" value={form.time_from} onChange={set('time_from')} />
              </Field>
              <Field label="Время до" htmlFor={id('time_to')} error={errors.time_to}>
                <Input id={id('time_to')} type="time" value={form.time_to} onChange={set('time_to')} />
              </Field>
            </>
          ) : null}
          <Field label="Вид работы" htmlFor={id('work_type')} error={errors.work_type} className={isTask ? 'sm:col-span-2' : 'sm:col-span-3'}>
            <Select id={id('work_type')} value={form.work_type} onChange={set('work_type')} options={options.work_types} />
          </Field>
        </div>

        <fieldset className="space-y-3">
          <legend className="mb-2 text-sm font-medium text-ink">{isTask ? 'Связано с' : 'С кем работали'}</legend>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Группа" htmlFor={id('group')} error={errors.group}>
              <Select
                id={id('group')}
                value={form.group}
                onChange={set('group')}
                placeholder="Не выбрана"
                options={options.groups.map((g) => ({ value: String(g.id), label: g.name }))}
              />
            </Field>
            <Field label="Тренер" htmlFor={id('teacher')} error={errors.teacher}>
              <Select
                id={id('teacher')}
                value={form.teacher}
                onChange={set('teacher')}
                placeholder="Не выбран"
                options={options.teachers.map((t) => ({ value: String(t.id), label: t.name }))}
              />
            </Field>
            <Field label="Студент" htmlFor={id('student')} error={errors.student}>
              <Select
                id={id('student')}
                value={form.student}
                onChange={set('student')}
                placeholder="Не выбран"
                options={students.map((s) => ({ value: String(s.id), label: s.name }))}
              />
            </Field>
          </div>
          {!isTask ? (
            <Field label="Другие участники" htmlFor={id('with_whom')} error={errors.with_whom}>
              <Input
                id={id('with_whom')}
                value={form.with_whom}
                onChange={set('with_whom')}
                placeholder="Команда тренеров, родители…"
              />
            </Field>
          ) : null}
        </fieldset>

        {!isTask ? (
          <>
            <Field label="Цель" htmlFor={id('goal')} error={errors.goal}>
              <Input id={id('goal')} value={form.goal} onChange={set('goal')} />
            </Field>
            <Field label="Что сделано" htmlFor={id('description')} error={errors.description} required>
              <Textarea id={id('description')} rows={3} value={form.description} onChange={set('description')} />
            </Field>
          </>
        ) : null}
        <Field label="Результат" htmlFor={id('result')} error={errors.result} required={!isTask}>
          <Textarea id={id('result')} rows={2} value={form.result} onChange={set('result')} />
        </Field>
        {!isTask ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Проблема" htmlFor={id('problem')} error={errors.problem}>
              <Textarea id={id('problem')} rows={2} value={form.problem} onChange={set('problem')} />
            </Field>
            <Field label="Решение" htmlFor={id('decision')} error={errors.decision}>
              <Textarea id={id('decision')} rows={2} value={form.decision} onChange={set('decision')} />
            </Field>
          </div>
        ) : null}
        {!isTask ? (
          <Field label="Что дальше" htmlFor={id('next_action')} error={errors.next_action} required>
            <Input
              id={id('next_action')}
              value={form.next_action}
              onChange={set('next_action')}
              placeholder="Повторная проверка через неделю"
            />
          </Field>
        ) : null}

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Ответственный" htmlFor={id('responsible')} error={errors.responsible} required={isTask}>
            <Input id={id('responsible')} value={form.responsible} onChange={set('responsible')} />
          </Field>
          <Field label="Срок" htmlFor={id('deadline')} error={errors.deadline} required={isTask}>
            <DatePicker id={id('deadline')} value={form.deadline} onChange={set('deadline')} />
          </Field>
          <Field label="Приоритет" htmlFor={id('priority')} error={errors.priority}>
            <Select id={id('priority')} value={form.priority} onChange={set('priority')} options={options.priorities} />
          </Field>
          <Field
            label="Статус"
            htmlFor={id('status')}
            error={errors.status}
            help="«Просрочено» ставится автоматически, когда срок прошёл."
          >
            <Select id={id('status')} value={form.status} onChange={set('status')} options={statusOptions} />
          </Field>
        </div>

        <Field label="Комментарий" htmlFor={id('comment')} error={errors.comment}>
          <Textarea id={id('comment')} rows={2} value={form.comment} onChange={set('comment')} />
        </Field>

        {generalError ? <p role="alert" className="text-sm text-danger">{generalError}</p> : null}

        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Отмена
          </Button>
          <Button type="submit" isLoading={save.isPending} leftIcon={<Save className="size-4" aria-hidden />}>
            Сохранить
          </Button>
        </div>
      </form>
    </Modal>
  )
}
