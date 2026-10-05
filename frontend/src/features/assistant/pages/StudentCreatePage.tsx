import { useState } from 'react'
import { UserPlus } from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { assistantApi } from '@/api/assistant'
import { PageHeader } from '@/components/layout/PageHeader'
import { BackLink } from '@/components/ui/BackLink'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { DatePicker } from '@/components/ui/DatePicker'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { useAssistantFormMutation, useAssistantOptions } from '@/hooks/useAssistant'
import { extractErrorMessage } from '@/lib/apiError'

import { Field, FormError, todayIso } from '../ui'

/**
 * «Добавить студента» — the minimum the academy needs: name, contacts, the
 * group (which fixes the program) and the start date. The student is
 * created active in that group by the backend's enrollment service.
 */
export function AssistantStudentCreatePage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const { data: options } = useAssistantOptions()
  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    phone: '',
    parent_phone: '',
    course: '',
    group: params.get('group') ?? '',
    enrollment_date: todayIso(),
  })
  const [another, setAnother] = useState(false)
  const set = (key: keyof typeof form) => (event: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: event.target.value }))

  const presetGroup = options?.groups.find((g) => String(g.id) === form.group)
  const courseFilter = form.course || (presetGroup ? String(options?.courses.find((c) => c.name === presetGroup.course)?.id ?? '') : '')
  const groups = (options?.groups ?? [])
    .filter((g) => !courseFilter || options?.courses.find((c) => String(c.id) === courseFilter)?.name === g.course)
    .map((g) => ({
      value: String(g.id),
      label: `${g.name} (${g.students_count}${g.max_students ? `/${g.max_students}` : ''})`,
    }))

  const mutation = useAssistantFormMutation(
    () => assistantApi.createStudent({
      first_name: form.first_name.trim(),
      last_name: form.last_name.trim(),
      phone: form.phone.trim(),
      parent_phone: form.parent_phone.trim(),
      group: Number(form.group),
      enrollment_date: form.enrollment_date || null,
    }),
    (student) => `Студент ${student.full_name} добавлен в ${student.group?.name ?? 'группу'}`,
  )
  const canSubmit = form.first_name.trim() !== '' && form.last_name.trim() !== '' && form.group !== ''

  return (
    <div className="mx-auto max-w-2xl">
      <BackLink to="/assistant/students">К списку студентов</BackLink>
      <PageHeader title="Добавить студента" description="Студент сразу становится активным в выбранной группе." />
      <Card>
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            if (!canSubmit) return
            mutation.mutate(undefined, {
              onSuccess: (student) => {
                if (another) setForm((f) => ({ ...f, first_name: '', last_name: '', phone: '', parent_phone: '' }))
                else navigate(`/assistant/students/${student.id}`)
              },
            })
          }}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Имя" htmlFor="student-first" required>
              <Input id="student-first" value={form.first_name} onChange={set('first_name')} autoFocus maxLength={100} />
            </Field>
            <Field label="Фамилия" htmlFor="student-last" required>
              <Input id="student-last" value={form.last_name} onChange={set('last_name')} maxLength={100} />
            </Field>
            <Field label="Телефон" htmlFor="student-phone">
              <Input id="student-phone" type="tel" value={form.phone} onChange={set('phone')} placeholder="+996 …" maxLength={30} />
            </Field>
            <Field label="Телефон родителя" htmlFor="student-parent-phone">
              <Input id="student-parent-phone" type="tel" value={form.parent_phone} onChange={set('parent_phone')} placeholder="+996 …" maxLength={30} />
            </Field>
            <Field label="Программа" htmlFor="student-course" required>
              <Select id="student-course" value={courseFilter} onChange={(e) => setForm((f) => ({ ...f, course: e.target.value, group: '' }))}
                placeholder="Выберите программу" options={(options?.courses ?? []).map((c) => ({ value: String(c.id), label: c.name }))} />
            </Field>
            <Field label="Группа" htmlFor="student-group" required>
              <Select id="student-group" value={form.group} onChange={set('group')} placeholder="Выберите группу" options={groups} />
            </Field>
            <Field label="Дата начала обучения" htmlFor="student-start" hint="От неё считается право на стипендию.">
              <DatePicker id="student-start" value={form.enrollment_date} onChange={set('enrollment_date')} />
            </Field>
          </div>
          <FormError message={mutation.error ? extractErrorMessage(mutation.error) : null} />
          <div className="flex flex-col gap-3 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between">
            <label className="flex items-center gap-2 text-sm text-ink">
              <input type="checkbox" className="size-4 accent-brand-500" checked={another} onChange={(e) => setAnother(e.target.checked)} />
              Добавить ещё одного после сохранения
            </label>
            <div className="flex flex-col-reverse gap-2 sm:flex-row">
              <Button type="button" variant="secondary" onClick={() => navigate('/assistant/students')}>Отмена</Button>
              <Button type="submit" disabled={!canSubmit || mutation.isPending} isLoading={mutation.isPending} leftIcon={<UserPlus className="size-4" aria-hidden />}>
                Добавить студента
              </Button>
            </div>
          </div>
        </form>
      </Card>
    </div>
  )
}
