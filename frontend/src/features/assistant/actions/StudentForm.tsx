import { useEffect, useState } from 'react'
import { CheckCircle2, ChevronDown, UserPlus } from 'lucide-react'
import { Link } from 'react-router-dom'

import { assistantApi } from '@/api/assistant'
import type { AccountCheck } from '@/api/assistant'
import { Button } from '@/components/ui/Button'
import { DatePicker } from '@/components/ui/DatePicker'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { useAssistantFormMutation, useAssistantOptions } from '@/hooks/useAssistant'
import { extractErrorMessage } from '@/lib/apiError'
import type { StudentDetail } from '@/types/assistant'

import { Field, FormError, todayIso } from '../ui'
import { CredentialsCard } from './StudentAccount'

/**
 * «Добавить студента» — required: name, parent phone, branch and group; the
 * rest is optional and folded away. The student is created active in that
 * group by the backend's enrollment service and, in the same transaction,
 * gets a Student & Parent Portal account (apps.portal) — or joins the
 * family account of a brother / sister with the same parent phone. The
 * temporary credentials are shown once, right here.
 * Used both as the /assistant/students/create page and as the quick modal.
 */
export function StudentForm({ presetGroup = '', onCancel, onOpen }: { presetGroup?: string; onCancel: () => void; onOpen?: () => void }) {
  const { data: options } = useAssistantOptions()
  const defaultBranch = options?.branches?.length === 1 ? String(options.branches[0].id) : ''
  const empty = {
    first_name: '', last_name: '', phone: '', parent_phone: '', parent_name: '', birth_date: '', course: '',
    group: presetGroup, branch: '', enrollment_date: todayIso(), login: '',
  }
  const [form, setForm] = useState(empty)
  const [more, setMore] = useState(false)
  const [photo, setPhoto] = useState<File | null>(null)
  const [accountMode, setAccountMode] = useState<string>('new') // 'new' | 'none' | <family account id>
  const [check, setCheck] = useState<AccountCheck | null>(null)
  const [created, setCreated] = useState<StudentDetail | null>(null)
  const set = (key: keyof typeof form) => (event: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: event.target.value }))
  const branch = form.branch || defaultBranch

  // Login preview + family accounts that already use this parent phone.
  useEffect(() => {
    if (!form.first_name.trim() && !form.parent_phone.trim()) {
      setCheck(null)
      return
    }
    const timer = window.setTimeout(() => {
      assistantApi
        .accountCheck({ first_name: form.first_name, last_name: form.last_name, parent_phone: form.parent_phone })
        .then(setCheck)
        .catch(() => setCheck(null))
    }, 400)
    return () => window.clearTimeout(timer)
  }, [form.first_name, form.last_name, form.parent_phone])

  // A family account found by phone is offered first; it disappears with the phone.
  const familyIds = (check?.family_accounts ?? []).map((a) => String(a.id)).join(',')
  useEffect(() => {
    const ids = familyIds ? familyIds.split(',') : []
    setAccountMode((mode) => {
      if (ids.length && mode === 'new') return ids[0]
      if (!['new', 'none'].includes(mode) && !ids.includes(mode)) return 'new'
      return mode
    })
  }, [familyIds])

  const groupCourse = options?.groups.find((g) => String(g.id) === form.group)?.course
  const courseFilter = form.course || String(options?.courses.find((c) => c.name === groupCourse)?.id ?? '')
  const courseName = options?.courses.find((c) => String(c.id) === courseFilter)?.name
  const groups = (options?.groups ?? [])
    .filter((g) => !courseName || g.course === courseName)
    .map((g) => ({ value: String(g.id), label: `${g.name} · ${g.course} (${g.students_count}${g.max_students ? `/${g.max_students}` : ''})` }))

  const mutation = useAssistantFormMutation(
    async () => {
      const linked = !['new', 'none'].includes(accountMode)
      const student = await assistantApi.createStudent({
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        phone: form.phone.trim(),
        parent_phone: form.parent_phone.trim(),
        parent_name: form.parent_name.trim(),
        birth_date: form.birth_date || null,
        branch: branch ? Number(branch) : null,
        group: Number(form.group),
        enrollment_date: form.enrollment_date || null,
        create_account: accountMode === 'new',
        login: accountMode === 'new' ? form.login.trim() : '',
        link_account: linked ? Number(accountMode) : null,
      })
      if (photo) {
        try {
          const withPhoto = await assistantApi.uploadPhoto(student.id, photo)
          return { ...withPhoto, credentials: student.credentials }
        } catch {
          return student // the student exists; the photo can be added on their page
        }
      }
      return student
    },
    (student) => `Студент ${student.full_name} создан`,
  )
  const branchRequired = (options?.branches?.length ?? 0) > 0
  const canSubmit = form.first_name.trim() !== '' && form.last_name.trim() !== '' && form.group !== ''
    && form.parent_phone.trim() !== '' && (!branchRequired || branch !== '')

  if (created) {
    return (
      <div className="space-y-4 text-center">
        <CheckCircle2 className="mx-auto size-10 text-brand-500" aria-hidden />
        <div>
          <p className="font-semibold text-ink">Студент успешно создан</p>
          <p className="text-sm text-ink-secondary">{created.full_name} · {created.group?.name}</p>
        </div>
        {created.credentials ? (
          <CredentialsCard credentials={created.credentials} studentName={created.full_name} />
        ) : created.account ? (
          <p className="rounded-lg bg-surface-muted px-3 py-2 text-sm text-ink-secondary">
            Добавлен в кабинет семьи <b className="font-mono text-ink">{created.account.login}</b> — родители увидят ребёнка
            со своим прежним паролем.
          </p>
        ) : null}
        <div className="flex flex-col-reverse justify-center gap-2 sm:flex-row">
          <Button variant="secondary" onClick={() => {
            setCreated(null); setPhoto(null); setAccountMode('new')
            setForm({ ...empty, group: form.group, course: form.course, branch: form.branch }); mutation.reset()
          }}>
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

  const family = check?.family_accounts ?? []
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
        <Field label="Телефон родителя" htmlFor="student-parent-phone" required>
          <Input id="student-parent-phone" type="tel" value={form.parent_phone} onChange={set('parent_phone')} placeholder="+996 …" maxLength={30} />
        </Field>
        <Field label="Филиал" htmlFor="student-branch" required={branchRequired}>
          <Select id="student-branch" value={branch} onChange={set('branch')} placeholder={branchRequired ? 'Выберите филиал' : 'Филиалы не заведены'}
            options={(options?.branches ?? []).map((b) => ({ value: String(b.id), label: b.name }))} />
        </Field>
        <Field label="Группа" htmlFor="student-group" required className="sm:col-span-2">
          <Select id="student-group" value={form.group} onChange={set('group')} placeholder="Выберите группу" options={groups} />
        </Field>
      </div>

      <button type="button" onClick={() => setMore((v) => !v)}
        className="flex items-center gap-1 text-sm font-medium text-brand-700 hover:text-brand-600" aria-expanded={more}>
        <ChevronDown className={`size-4 transition-transform ${more ? 'rotate-180' : ''}`} aria-hidden />
        Дополнительно: дата рождения, фото, имя родителя
      </button>
      {more ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Имя родителя" htmlFor="student-parent-name">
            <Input id="student-parent-name" value={form.parent_name} onChange={set('parent_name')} maxLength={150} />
          </Field>
          <Field label="Дата рождения" htmlFor="student-birth">
            <DatePicker id="student-birth" value={form.birth_date} onChange={set('birth_date')} />
          </Field>
          <Field label="Телефон ученика" htmlFor="student-phone">
            <Input id="student-phone" type="tel" value={form.phone} onChange={set('phone')} placeholder="+996 …" maxLength={30} />
          </Field>
          <Field label="Фото" htmlFor="student-photo" hint="JPG или PNG, до 5 МБ.">
            <input id="student-photo" type="file" accept="image/*"
              className="block w-full text-sm text-ink-secondary file:mr-3 file:rounded-lg file:border-0 file:bg-brand-50 file:px-3 file:py-2 file:text-sm file:font-medium file:text-brand-700"
              onChange={(event) => setPhoto(event.target.files?.[0] ?? null)} />
          </Field>
          <Field label="Программа" htmlFor="student-course" hint="Сужает список групп.">
            <Select id="student-course" value={courseFilter} onChange={(e) => setForm((f) => ({ ...f, course: e.target.value, group: '' }))}
              placeholder="Все программы" options={(options?.courses ?? []).map((c) => ({ value: String(c.id), label: c.name }))} />
          </Field>
          <Field label="Дата начала обучения" htmlFor="student-start" hint="От неё считается право на стипендию.">
            <DatePicker id="student-start" value={form.enrollment_date} onChange={set('enrollment_date')} />
          </Field>
        </div>
      ) : null}

      <fieldset className="rounded-xl border border-border p-3">
        <legend className="px-1 text-sm font-medium text-ink">Кабинет ученика и родителя</legend>
        <div className="space-y-2 text-sm">
          {family.map((account) => (
            <label key={account.id} className="flex items-start gap-2">
              <input type="radio" name="account-mode" className="mt-1 accent-brand-500" checked={accountMode === String(account.id)}
                onChange={() => setAccountMode(String(account.id))} />
              <span>Добавить в кабинет семьи <b className="font-mono">{account.login}</b>
                <span className="text-ink-secondary"> · {account.students.join(', ')}</span></span>
            </label>
          ))}
          <label className="flex items-start gap-2">
            <input type="radio" name="account-mode" className="mt-1 accent-brand-500" checked={accountMode === 'new'} onChange={() => setAccountMode('new')} />
            <span>Создать новый кабинет{check?.suggested_login && !form.login ? <> — логин <b className="font-mono">{check.suggested_login}</b></> : null}</span>
          </label>
          {accountMode === 'new' && more ? (
            <Input aria-label="Свой логин" value={form.login} onChange={(e) => setForm((f) => ({ ...f, login: e.target.value.toLowerCase() }))}
              placeholder={check?.suggested_login ? `Свой логин вместо ${check.suggested_login}` : 'Свой логин (необязательно)'} maxLength={40} />
          ) : null}
          <label className="flex items-start gap-2">
            <input type="radio" name="account-mode" className="mt-1 accent-brand-500" checked={accountMode === 'none'} onChange={() => setAccountMode('none')} />
            <span className="text-ink-secondary">Без кабинета (можно создать позже)</span>
          </label>
        </div>
      </fieldset>

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
