import { useState } from 'react'
import { CheckCircle2, UserPlus } from 'lucide-react'
import { Link } from 'react-router-dom'

import { assistantApi } from '@/api/assistant'
import { Button } from '@/components/ui/Button'
import { DatePicker } from '@/components/ui/DatePicker'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { useAssistantFormMutation, useAssistantOptions } from '@/hooks/useAssistant'
import { extractErrorMessage } from '@/lib/apiError'
import type { StudentDetail } from '@/types/assistant'

import { Field, FormError, todayIso } from '../ui'

/**
 * «Добавить студента» — required: name and group; the rest is optional. The
 * student is created active in that group by the backend's enrollment
 * service. After saving: «Открыть студента» or «Добавить ещё».
 * Used both as the /assistant/students/create page and as the quick modal.
 */
export function StudentForm({ presetGroup = '', onCancel, onOpen }: { presetGroup?: string; onCancel: () => void; onOpen?: () => void }) {
  const { data: options } = useAssistantOptions()
  const empty = { first_name: '', last_name: '', phone: '', parent_phone: '', course: '', group: presetGroup, enrollment_date: todayIso() }
  const [form, setForm] = useState(empty)
  const [created, setCreated] = useState<StudentDetail | null>(null)
  const set = (key: keyof typeof form) => (event: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: event.target.value }))

  const groupCourse = options?.groups.find((g) => String(g.id) === form.group)?.course
  const courseFilter = form.course || String(options?.courses.find((c) => c.name === groupCourse)?.id ?? '')
  const courseName = options?.courses.find((c) => String(c.id) === courseFilter)?.name
  const groups = (options?.groups ?? [])
    .filter((g) => !courseName || g.course === courseName)
    .map((g) => ({ value: String(g.id), label: `${g.name} · ${g.course} (${g.students_count}${g.max_students ? `/${g.max_students}` : ''})` }))

  const mutation = useAssistantFormMutation(
    () => assistantApi.createStudent({
      first_name: form.first_name.trim(),
      last_name: form.last_name.trim(),
      phone: form.phone.trim(),
      parent_phone: form.parent_phone.trim(),
      group: Number(form.group),
      enrollment_date: form.enrollment_date || null,
    }),
    (student) => `Студент ${student.full_name} создан`,
  )
  const canSubmit = form.first_name.trim() !== '' && form.last_name.trim() !== '' && form.group !== ''

  if (created) {
    return (
      <div className="space-y-4 text-center">
        <CheckCircle2 className="mx-auto size-10 text-brand-500" aria-hidden />
        <div>
          <p className="font-semibold text-ink">Студент успешно создан</p>
          <p className="text-sm text-ink-secondary">{created.full_name} · {created.group?.name}</p>
        </div>
        <div className="flex flex-col-reverse justify-center gap-2 sm:flex-row">
          <Button variant="secondary" onClick={() => { setCreated(null); setForm({ ...empty, group: form.group, course: form.course }); mutation.reset() }}>
            Добавить ещё
          </Button>
          <Link to={`/assistant/students/${created.id}`} onClick={onOpen}
            className="inline-flex h-10 items-center justify-center rounded-lg bg-brand-500 px-4 text-sm font-medium text-white hover:bg-brand-600">
            Открыть студента
          </Link>
        </div>
      </div>
    )
  }

  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault()
        if (canSubmit) mutation.mutate(undefined, { onSuccess: setCreated })
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Имя" htmlFor="student-first" required>
          <Input id="student-first" value={form.first_name} onChange={set('first_name')} autoFocus maxLength={100} />
        </Field>
        <Field label="Фамилия" htmlFor="student-last" required>
          <Input id="student-last" value={form.last_name} onChange={set('last_name')} maxLength={100} />
        </Field>
        <Field label="Группа" htmlFor="student-group" required className="sm:col-span-2">
          <Select id="student-group" value={form.group} onChange={set('group')} placeholder="Выберите группу" options={groups} />
        </Field>
        <Field label="Телефон" htmlFor="student-phone">
          <Input id="student-phone" type="tel" value={form.phone} onChange={set('phone')} placeholder="+996 …" maxLength={30} />
        </Field>
        <Field label="Телефон родителя" htmlFor="student-parent-phone">
          <Input id="student-parent-phone" type="tel" value={form.parent_phone} onChange={set('parent_phone')} placeholder="+996 …" maxLength={30} />
        </Field>
        <Field label="Программа" htmlFor="student-course" hint="Сужает список групп.">
          <Select id="student-course" value={courseFilter} onChange={(e) => setForm((f) => ({ ...f, course: e.target.value, group: '' }))}
            placeholder="Все программы" options={(options?.courses ?? []).map((c) => ({ value: String(c.id), label: c.name }))} />
        </Field>
        <Field label="Дата начала обучения" htmlFor="student-start" hint="От неё считается право на стипендию.">
          <DatePicker id="student-start" value={form.enrollment_date} onChange={set('enrollment_date')} />
        </Field>
      </div>
      <FormError message={mutation.error ? extractErrorMessage(mutation.error) : null} />
      <div className="flex flex-col-reverse gap-2 border-t border-border pt-4 sm:flex-row sm:justify-end">
        <Button type="button" variant="secondary" onClick={onCancel}>Отмена</Button>
        <Button type="submit" disabled={!canSubmit || mutation.isPending} isLoading={mutation.isPending} leftIcon={<UserPlus className="size-4" aria-hidden />}>
          Добавить студента
        </Button>
      </div>
    </form>
  )
}
