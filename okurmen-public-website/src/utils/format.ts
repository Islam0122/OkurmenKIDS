import type { Translate } from '@/i18n'

export function ageRange(t: Translate, min: number | null, max: number | null): string | null {
  if (min && max) return t('courses.ageRange', { from: min, to: max })
  if (min) return t('courses.ageFrom', { from: min })
  if (max) return t('courses.ageTo', { to: max })
  return null
}

/** «+996 555 12 34 56» → tel:+996555123456 */
export function telHref(phone: string): string {
  return `tel:${phone.replace(/[^\d+]/g, '')}`
}

export function excerpt(text: string, max = 160): string {
  const clean = text.replace(/[#>*_`[\]()!-]/g, ' ').replace(/\s+/g, ' ').trim()
  return clean.length > max ? `${clean.slice(0, max - 1).trimEnd()}…` : clean
}
