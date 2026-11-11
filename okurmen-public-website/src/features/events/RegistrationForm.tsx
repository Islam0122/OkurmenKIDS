import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Loader2 } from 'lucide-react'
import { useMemo } from 'react'
import { useForm, type Path } from 'react-hook-form'

import { Field, Honeypot } from '@/components/forms/Field'
import { Button } from '@/components/shared/Button'
import { registrationSchema, type RegistrationForm as Values } from '@/features/enrollment/schema'
import { useI18n } from '@/i18n'
import { ApiError } from '@/services/api/client'
import { siteApi } from '@/services/endpoints'
import type { SubmitResult } from '@/types/api'

/** Registration for an event (POST /site/events/<slug>/register/) — only rendered while registration is open. */
export function RegistrationForm({ slug }: { slug: string }) {
  const { t } = useI18n()
  const client = useQueryClient()
  const schema = useMemo(() => registrationSchema(t), [t])
  const { register, handleSubmit, formState: { errors }, setError } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { parent_name: '', phone: '', child_name: '', child_age: '', comment: '', website: '' } })
  const mutation = useMutation<SubmitResult, ApiError, Values>({
    mutationFn: (v) => siteApi.register(slug, {
      parent_name: v.parent_name.trim(),
      phone: v.phone.trim(),
      child_name: v.child_name?.trim() || undefined,
      child_age: v.child_age === '' || v.child_age === undefined ? null : Number(v.child_age),
      comment: v.comment?.trim() || undefined,
      website: v.website,
    }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['event', slug] }),
    onError: (error) => {
      if (error.kind === 'validation') for (const [f, m] of Object.entries(error.fields)) if (f in schema.shape) setError(f as Path<Values>, { message: m[0] })
    },
  })

  if (mutation.isSuccess) {
    return (
      <div role="status" className="flex flex-col items-center gap-3 py-4 text-center">
        <CheckCircle2 className="size-12 text-success" aria-hidden />
        <p className="font-display text-lg font-extrabold">{mutation.data.duplicate ? t('form.success.duplicate') : t('form.registered')}</p>
      </div>
    )
  }

  return (
    <form noValidate onSubmit={handleSubmit((v) => !mutation.isPending && mutation.mutate(v))} className="relative space-y-4">
      <Honeypot register={register('website')} />
      <Field id="reg-name" label={t('form.parentName')} error={errors.parent_name?.message}>
        <input id="reg-name" className="input" autoComplete="name" aria-invalid={!!errors.parent_name} {...register('parent_name')} />
      </Field>
      <Field id="reg-phone" label={t('form.phone')} error={errors.phone?.message}>
        <input id="reg-phone" type="tel" inputMode="tel" autoComplete="tel" className="input" placeholder={t('form.phonePlaceholder')} aria-invalid={!!errors.phone} {...register('phone')} />
      </Field>
      <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,6.5rem)] items-end gap-3">
        <Field id="reg-child" label={t('form.childName')} optional>
          <input id="reg-child" className="input" {...register('child_name')} />
        </Field>
        <Field id="reg-age" label={t('form.childAgePlaceholder')} error={errors.child_age?.message} optional>
          <input id="reg-age" type="number" inputMode="numeric" min={3} max={25} className="input" {...register('child_age')} />
        </Field>
      </div>
      <Field id="reg-comment" label={t('form.comment')} optional>
        <textarea id="reg-comment" rows={2} className="input" {...register('comment')} />
      </Field>
      {mutation.isError && mutation.error.kind !== 'validation' ? (
        <p role="alert" className="rounded-xl bg-orange-50 px-4 py-3 text-sm font-medium text-danger">
          {mutation.error.kind === 'conflict' ? t('form.error.closed') : mutation.error.kind === 'rate_limited' ? t('state.error.rate') : t('form.error.generic')}
        </p>
      ) : null}
      <Button type="submit" className="w-full" disabled={mutation.isPending}>
        {mutation.isPending ? <Loader2 className="size-4 animate-spin" aria-hidden /> : null}
        {mutation.isPending ? t('form.submitting') : t('cta.register')}
      </Button>
      <p className="text-center text-xs text-muted">{t('form.consent')}</p>
    </form>
  )
}
