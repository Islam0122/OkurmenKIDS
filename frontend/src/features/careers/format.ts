import type { PublicSalary } from '@/types/careers'

const NUMBER = new Intl.NumberFormat('ru-RU')

export function formatSalary(salary: PublicSalary | null): string | null {
  if (!salary) return null
  const unit = salary.currency_label
  if (salary.min !== null && salary.max !== null) {
    return salary.min === salary.max
      ? `${NUMBER.format(salary.min)} ${unit}`
      : `${NUMBER.format(salary.min)} – ${NUMBER.format(salary.max)} ${unit}`
  }
  if (salary.min !== null) return `от ${NUMBER.format(salary.min)} ${unit}`
  if (salary.max !== null) return `до ${NUMBER.format(salary.max)} ${unit}`
  return null
}

export function formatPublished(iso: string | null): string {
  if (!iso) return ''
  return new Date(`${iso}T00:00:00`).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })
}

/** Ключ формы отклика: повторная отправка той же формы не создаст вторую заявку. */
export function newSubmissionToken(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
