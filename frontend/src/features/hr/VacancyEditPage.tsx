import { useState, type FormEvent } from 'react'
import { ExternalLink } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { BackLink } from '@/components/ui/BackLink'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { DatePicker } from '@/components/ui/DatePicker'
import { ErrorState } from '@/components/ui/ErrorState'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { useRecruitmentMeta, useSaveVacancy, useVacancy } from '@/hooks/useHr'
import { extractErrorMessage } from '@/lib/apiError'
import type { RecruitmentMeta, Vacancy, VacancyInput } from '@/types/hr'
import { formatDateShort } from '@/utils/format'

import { Field, FormError, VACANCY_TONE, officeDate } from './shared'
import { STATUS_ACTIONS, useVacancyStatusAction } from './VacanciesPage'

const EMPTY: VacancyInput = {
  title: '', slug: '', department: '', summary: '', description: '', responsibilities: '', requirements: '', nice_to_have: '',
  conditions: '', selection_stages: '', location: '', work_format: 'office', employment_type: 'full_time', salary_min: null,
  salary_max: null, salary_currency: 'KGS', show_salary: false, closes_on: null, responsible: null,
}

function fromVacancy(v: Vacancy): VacancyInput {
  return Object.fromEntries(Object.keys(EMPTY).map((key) => [key, v[key as keyof VacancyInput]])) as unknown as VacancyInput
}

/** /hr/vacancies/new и /hr/vacancies/:id — карточка вакансии. Сохранение не
 * публикует: на сайт вакансия попадает только кнопкой «Опубликовать». */
export function HrVacancyEditPage() {
  const param = useParams().id
  const id = param && param !== 'new' ? Number(param) : null
  const vacancy = useVacancy(id)
  const meta = useRecruitmentMeta()
  if ((id !== null && vacancy.isPending) || meta.isPending) return <LoadingState label="Загружаем вакансию…" />
  if (vacancy.isError) return <ErrorState title="Вакансия недоступна" message={extractErrorMessage(vacancy.error)} onRetry={() => void vacancy.refetch()} />
  if (meta.isError) return <ErrorState message={extractErrorMessage(meta.error)} onRetry={() => void meta.refetch()} />
  return <VacancyEditor key={vacancy.data?.id ?? 'new'} vacancy={vacancy.data ?? null} meta={meta.data} />
}

function VacancyEditor({ vacancy, meta }: { vacancy: Vacancy | null; meta: RecruitmentMeta }) {
  const navigate = useNavigate()
  const { showToast } = useToast()
  const save = useSaveVacancy()
  const action = useVacancyStatusAction()
  const [form, setForm] = useState<VacancyInput>(vacancy ? fromVacancy(vacancy) : EMPTY)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const set = (key: keyof VacancyInput) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }))
  const setNumber = (key: 'salary_min' | 'salary_max') => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value === '' ? null : Math.max(0, Math.round(Number(e.target.value))) }))

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    const found: Record<string, string> = {}
    if (!form.title.trim()) found.title = 'Укажите название.'
    if (form.salary_min !== null && form.salary_max !== null && form.salary_min > form.salary_max) found.salary_max = '«До» должно быть не меньше «от».'
    if (form.show_salary && form.salary_min === null && form.salary_max === null) found.show_salary = 'Укажите зарплату, чтобы её публиковать.'
    setErrors(found)
    if (Object.keys(found).length) return
    try {
      const saved = await save.mutateAsync({
        id: vacancy?.id,
        payload: { ...form, title: form.title.trim(), slug: form.slug.trim(), closes_on: form.closes_on || null },
      })
      showToast(vacancy ? 'Вакансия сохранена' : 'Черновик вакансии создан', 'success')
      if (!vacancy) navigate(`/hr/vacancies/${saved.id}`, { replace: true })
    } catch (err) {
      setError(extractErrorMessage(err))
    }
  }

  return (
    <form onSubmit={submit} className="space-y-5" noValidate>
      <BackLink to="/hr/vacancies">Вакансии</BackLink>
      <Card>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold text-ink sm:text-2xl">{vacancy ? vacancy.title : 'Новая вакансия'}</h1>
            {vacancy ? (
              <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-ink-secondary">
                <Badge tone={VACANCY_TONE[vacancy.status]}>{vacancy.status_label}</Badge>
                <span>создана {formatDateShort(officeDate(vacancy.created_at))}</span>
                {vacancy.published_at ? <span>· опубликована {formatDateShort(officeDate(vacancy.published_at))}</span> : null}
                {vacancy.closed_at ? <span>· закрыта {formatDateShort(officeDate(vacancy.closed_at))}</span> : null}
                <Link className="text-brand-700 hover:underline" to={`/hr/candidates?vacancy=${vacancy.id}`}>· откликов: {vacancy.applications_count}</Link>
              </div>
            ) : <p className="mt-1 text-sm text-ink-secondary">Сохранится черновиком. На сайте вакансия появится только после публикации.</p>}
          </div>
          {vacancy ? (
            <div className="flex flex-wrap gap-2">
              {vacancy.status === 'published' ? (
                <a href={`/careers/vacancies/${vacancy.slug}`} target="_blank" rel="noreferrer"
                  className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-brand-200 px-3 text-sm font-medium text-brand-700 hover:bg-brand-50">
                  <ExternalLink className="size-4" aria-hidden />На сайте
                </a>
              ) : null}
              {vacancy.allowed_statuses.map((s) => {
                const Icon = STATUS_ACTIONS[s.value].icon
                return (
                  <Button key={s.value} type="button" size="sm" variant={s.value === 'published' ? 'primary' : 'secondary'}
                    leftIcon={<Icon className="size-4" aria-hidden />} onClick={() => action.ask(vacancy, s.value)}
                    disabled={s.value === 'published' && vacancy.missing_for_publishing.length > 0}>
                    {action.label(vacancy, s.value)}
                  </Button>
                )
              })}
            </div>
          ) : null}
        </div>
        {vacancy && vacancy.missing_for_publishing.length && vacancy.allowed_statuses.some((s) => s.value === 'published') ? (
          <p className="mt-3 rounded-xl bg-warning-soft px-3 py-2 text-sm text-warning">
            Для публикации заполните и сохраните: {vacancy.missing_for_publishing.join(', ')}.
          </p>
        ) : null}
      </Card>

      <Card title="Основное">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Field id="vac-title" label="Название" required>
              <Input id="vac-title" value={form.title} onChange={set('title')} maxLength={200} aria-invalid={Boolean(errors.title)} />
            </Field>
            {errors.title ? <p className="mt-1 text-xs text-danger">{errors.title}</p> : null}
          </div>
          <Field id="vac-dep" label="Направление или отдел"><Input id="vac-dep" value={form.department} onChange={set('department')} maxLength={150} /></Field>
          <Field id="vac-location" label="Город или место работы"><Input id="vac-location" value={form.location} onChange={set('location')} maxLength={150} /></Field>
          <Field id="vac-format" label="Формат работы" required><Select id="vac-format" value={form.work_format} onChange={set('work_format')} options={meta.work_formats} /></Field>
          <Field id="vac-type" label="Тип занятости" required><Select id="vac-type" value={form.employment_type} onChange={set('employment_type')} options={meta.employment_types} /></Field>
          <Field id="vac-resp" label="Ответственный">
            <Select id="vac-resp" value={form.responsible ? String(form.responsible) : ''} onChange={(e) => setForm((f) => ({ ...f, responsible: e.target.value ? Number(e.target.value) : null }))}
              placeholder="Не назначен" options={meta.people.map((p) => ({ value: String(p.id), label: `${p.full_name} · ${p.role_label}` }))} />
          </Field>
          <Field id="vac-closes" label="Приём откликов до" hint="Пусто — без срока">
            <DatePicker id="vac-closes" value={form.closes_on ?? ''} min={meta.today} onChange={(e) => setForm((f) => ({ ...f, closes_on: e.target.value || null }))} />
          </Field>
          <Field id="vac-slug" label="Адрес на сайте" hint={`/careers/vacancies/${form.slug || 'создаётся из названия'}`}>
            <Input id="vac-slug" value={form.slug} onChange={set('slug')} maxLength={80} placeholder="sales-manager" />
          </Field>
          <Field id="vac-summary" label="Краткое описание" hint="Строка в списке вакансий">
            <Input id="vac-summary" value={form.summary} onChange={set('summary')} maxLength={300} />
          </Field>
        </div>
      </Card>

      <Card title="Зарплата">
        <div className="grid gap-3 sm:grid-cols-3">
          <Field id="vac-salary-min" label="От"><Input id="vac-salary-min" type="number" min={0} value={form.salary_min ?? ''} onChange={setNumber('salary_min')} /></Field>
          <div>
            <Field id="vac-salary-max" label="До"><Input id="vac-salary-max" type="number" min={0} value={form.salary_max ?? ''} onChange={setNumber('salary_max')} /></Field>
            {errors.salary_max ? <p className="mt-1 text-xs text-danger">{errors.salary_max}</p> : null}
          </div>
          <Field id="vac-currency" label="Валюта"><Select id="vac-currency" value={form.salary_currency} onChange={set('salary_currency')} options={meta.currencies} /></Field>
        </div>
        <label className="mt-3 flex items-center gap-2 text-sm text-ink">
          <input type="checkbox" className="size-4 accent-brand-600" checked={form.show_salary} onChange={(e) => setForm((f) => ({ ...f, show_salary: e.target.checked }))} />
          Публиковать зарплату на сайте
        </label>
        {errors.show_salary ? <p className="mt-1 text-xs text-danger">{errors.show_salary}</p> : null}
      </Card>

      <Card title="Содержание" description="Списки — по одному пункту в строке: на сайте каждая строка станет отдельным пунктом">
        <div className="space-y-3">
          <Field id="vac-desc" label="Описание"><Textarea id="vac-desc" rows={4} value={form.description} onChange={set('description')} /></Field>
          <div className="grid gap-3 lg:grid-cols-2">
            <Field id="vac-resps" label="Обязанности"><Textarea id="vac-resps" rows={5} value={form.responsibilities} onChange={set('responsibilities')} /></Field>
            <Field id="vac-reqs" label="Обязательные требования"><Textarea id="vac-reqs" rows={5} value={form.requirements} onChange={set('requirements')} /></Field>
            <Field id="vac-nice" label="Желательные навыки"><Textarea id="vac-nice" rows={4} value={form.nice_to_have} onChange={set('nice_to_have')} /></Field>
            <Field id="vac-cond" label="Условия работы"><Textarea id="vac-cond" rows={4} value={form.conditions} onChange={set('conditions')} /></Field>
          </div>
          <Field id="vac-stages" label="Этапы отбора"><Textarea id="vac-stages" rows={3} value={form.selection_stages} onChange={set('selection_stages')} placeholder={'Знакомство с HR\nВстреча с руководителем'} /></Field>
        </div>
      </Card>

      <FormError message={error} />
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button type="button" variant="ghost" onClick={() => navigate('/hr/vacancies')}>К списку</Button>
        <Button type="submit" isLoading={save.isPending}>{vacancy ? 'Сохранить' : 'Сохранить черновик'}</Button>
      </div>
      {action.dialog}
    </form>
  )
}
