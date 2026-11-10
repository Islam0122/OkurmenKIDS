import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation } from '@tanstack/react-query'
import { CheckCircle2, Loader2, MessageCircle, Phone, Send } from 'lucide-react'
import { useEffect, useMemo } from 'react'
import { useForm, type Path } from 'react-hook-form'
import { useLocation } from 'react-router-dom'

import { Field, Honeypot } from '@/components/forms/Field'
import { Button } from '@/components/shared/Button'
import { useCourses, useSettings } from '@/hooks/queries'
import { useI18n } from '@/i18n'
import { ApiError } from '@/services/api/client'
import { siteApi } from '@/services/endpoints'
import type { ContactMethod, SubmitResult } from '@/types/api'
import { cn } from '@/utils/cn'

import { leadSchema, type LeadForm } from './schema'
import { storedUtm } from './utm'

const METHODS: { value: ContactMethod; icon: typeof Phone }[] = [
  { value: 'phone', icon: Phone },
  { value: 'whatsapp', icon: MessageCircle },
  { value: 'telegram', icon: Send },
]

/**
 * «Записать ребёнка» — validated on the client (zod, same rules as the
 * backend), sent to POST /api/v1/public/site/leads/. The button is locked
 * while sending; the server merges repeats from the same phone (24 h).
 */
export function EnrollmentForm({ defaultCourse, compact, onDone }: { defaultCourse?: string; compact?: boolean; onDone?: () => void }) {
  const { t, lang } = useI18n()
  const location = useLocation()
  const courses = useCourses()
  const settings = useSettings()
  const schema = useMemo(() => leadSchema(t), [t])
  const form = useForm<LeadForm>({
    resolver: zodResolver(schema),
    defaultValues: { parent_name: '', phone: '', course: defaultCourse ?? '', branch: '', contact_method: 'whatsapp', message: '', website: '' },
  })
  const { register, handleSubmit, formState, setError, watch, setValue, reset } = form
  const errors = formState.errors

  const mutation = useMutation<SubmitResult, ApiError, LeadForm>({
    mutationFn: (values) =>
      siteApi.lead({
        parent_name: values.parent_name.trim(),
        phone: values.phone.trim(),
        child_age: values.child_age,
        course: values.course || undefined,
        branch: values.branch ? Number(values.branch) : null,
        contact_method: values.contact_method,
        message: values.message?.trim() || undefined,
        website: values.website,
        language: lang,
        source: location.pathname.slice(0, 200),
        ...storedUtm(),
      }),
    onError: (error) => {
      if (error.kind === 'validation') {
        for (const [field, messages] of Object.entries(error.fields)) {
          if (field in schema.shape) setError(field as Path<LeadForm>, { message: messages[0] })
        }
      }
    },
  })

  // Options arrive after the form mounts: re-apply the pre-selected course once they exist.
  const courseCount = courses.data?.results.length ?? 0
  useEffect(() => {
    if (defaultCourse && courseCount) setValue('course', defaultCourse)
  }, [defaultCourse, courseCount, setValue])

  if (mutation.isSuccess) {
    return (
      <div role="status" className="flex flex-col items-center gap-4 py-6 text-center">
        <span className="grid size-16 place-items-center rounded-full bg-emerald-50 text-success">
          <CheckCircle2 className="size-9" aria-hidden />
        </span>
        <div>
          <p className="font-display text-2xl font-extrabold">{t('form.success.title')}</p>
          <p className="mt-2 text-muted">{mutation.data.duplicate ? t('form.success.duplicate') : t('form.success.text')}</p>
        </div>
        {onDone ? (
          <Button variant="outline" onClick={onDone}>{t('cta.back')}</Button>
        ) : (
          <Button variant="ghost" onClick={() => { reset(); mutation.reset() }}>{t('form.success.again')}</Button>
        )}
      </div>
    )
  }

  const method = watch('contact_method')
  const generalError = mutation.isError && mutation.error.kind !== 'validation'
  const courseList = courses.data?.results ?? []
  const branches = settings.data?.branches ?? []

  return (
    <form noValidate onSubmit={handleSubmit((values) => !mutation.isPending && mutation.mutate(values))} className="relative space-y-4" aria-busy={mutation.isPending}>
      <Honeypot register={register('website')} />
      <div className={cn('grid gap-4', !compact && 'sm:grid-cols-2')}>
        <Field id="lead-name" label={t('form.parentName')} error={errors.parent_name?.message}>
          <input id="lead-name" autoComplete="name" className="input" placeholder={t('form.parentNamePlaceholder')} aria-invalid={!!errors.parent_name} aria-describedby={errors.parent_name ? 'lead-name-error' : undefined} {...register('parent_name')} />
        </Field>
        <Field id="lead-phone" label={t('form.phone')} error={errors.phone?.message}>
          <input id="lead-phone" type="tel" inputMode="tel" autoComplete="tel" className="input" placeholder={t('form.phonePlaceholder')} aria-invalid={!!errors.phone} aria-describedby={errors.phone ? 'lead-phone-error' : undefined} {...register('phone')} />
        </Field>
        <Field id="lead-age" label={t('form.childAge')} error={errors.child_age?.message}>
          <input id="lead-age" type="number" inputMode="numeric" min={3} max={25} className="input" placeholder={t('form.childAgePlaceholder')} aria-invalid={!!errors.child_age} {...register('child_age')} />
        </Field>
        <Field id="lead-course" label={t('form.course')} optional>
          <select id="lead-course" className="input" {...register('course')}>
            <option value="">{t('form.courseAny')}</option>
            {courseList.map((course) => (
              <option key={course.slug} value={course.slug}>{course.title}</option>
            ))}
          </select>
        </Field>
        {branches.length > 0 ? (
          <Field id="lead-branch" label={t('form.branch')} optional className={cn(!compact && 'sm:col-span-2')}>
            <select id="lead-branch" className="input" {...register('branch')}>
              <option value="">{t('form.branchAny')}</option>
              {branches.map((branch) => (
                <option key={branch.id} value={branch.id}>{branch.name} — {branch.address}</option>
              ))}
            </select>
          </Field>
        ) : null}
      </div>

      <fieldset>
        <legend className="mb-1.5 text-sm font-bold">{t('form.contactMethod')}</legend>
        <div className="grid grid-cols-3 gap-2">
          {METHODS.map(({ value, icon: Icon }) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={method === value}
              onClick={() => setValue('contact_method', value)}
              className={cn(
                'flex h-12 items-center justify-center gap-2 rounded-xl border text-sm font-bold transition',
                method === value ? 'border-brand-700 bg-brand-50 text-brand-800 ring-2 ring-brand-200' : 'border-line bg-white text-ink-soft hover:border-brand-300',
              )}
            >
              <Icon className="size-4" aria-hidden />
              <span className="truncate">{t(`form.contact.${value}`)}</span>
            </button>
          ))}
        </div>
      </fieldset>

      <Field id="lead-message" label={t('form.message')} optional>
        <textarea id="lead-message" rows={compact ? 2 : 3} className="input resize-y" placeholder={t('form.messagePlaceholder')} {...register('message')} />
      </Field>

      {generalError ? (
        <p role="alert" className="rounded-xl bg-orange-50 px-4 py-3 text-sm font-medium text-danger">
          {mutation.error.kind === 'rate_limited' ? t('state.error.rate') : t('form.error.generic')}
        </p>
      ) : null}

      <Button type="submit" size="lg" className="w-full" disabled={mutation.isPending}>
        {mutation.isPending ? <Loader2 className="size-5 animate-spin" aria-hidden /> : null}
        {mutation.isPending ? t('form.submitting') : t('form.submit')}
      </Button>
      <p className="text-center text-xs text-muted">{t('form.consent')}</p>
    </form>
  )
}
