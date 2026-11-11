import { z } from 'zod'

import type { Translate } from '@/i18n'

const phoneDigits = (value: string) => value.replace(/\D/g, '')

/** Same rules as the backend serializer (apps.website.public_views.LeadSerializer). */
export function leadSchema(t: Translate) {
  return z.object({
    parent_name: z.string().trim().min(2, t('form.error.name')).max(120),
    phone: z
      .string()
      .trim()
      .min(1, t('form.error.required'))
      .refine((v) => {
        const d = phoneDigits(v)
        return d.length >= 9 && d.length <= 15
      }, t('form.error.phone')),
    child_age: z.coerce.number({ invalid_type_error: t('form.error.age') }).int().min(3, t('form.error.age')).max(25, t('form.error.age')),
    course: z.string().optional(),
    branch: z.string().optional(),
    contact_method: z.enum(['phone', 'whatsapp', 'telegram']),
    message: z.string().max(2000).optional(),
    website: z.string().optional(),
  })
}

export type LeadForm = z.infer<ReturnType<typeof leadSchema>>

export function registrationSchema(t: Translate) {
  return z.object({
    parent_name: z.string().trim().min(2, t('form.error.name')).max(120),
    phone: z
      .string()
      .trim()
      .min(1, t('form.error.required'))
      .refine((v) => {
        const d = phoneDigits(v)
        return d.length >= 9 && d.length <= 15
      }, t('form.error.phone')),
    child_name: z.string().max(120).optional(),
    child_age: z.union([z.literal(''), z.coerce.number().int().min(3, t('form.error.age')).max(25, t('form.error.age'))]).optional(),
    comment: z.string().max(1000).optional(),
    website: z.string().optional(),
  })
}

export type RegistrationForm = z.infer<ReturnType<typeof registrationSchema>>
