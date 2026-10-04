import type { ReactNode } from 'react'
import { AxiosError } from 'axios'

import { cn } from '@/utils/cn'

/** DRF field errors as {field: message}; report data errors come back as
 * `{data: {key: [...]}}` and are keyed `data.<key>`. */
export function fieldErrors(error: unknown): Record<string, string> {
  if (!(error instanceof AxiosError)) return {}
  const body = error.response?.data
  if (!body || typeof body !== 'object' || Array.isArray(body)) return {}
  const out: Record<string, string> = {}
  const walk = (value: unknown, key: string) => {
    if (Array.isArray(value)) out[key] = value.map(String).join(' ')
    else if (value && typeof value === 'object') {
      for (const [k, v] of Object.entries(value)) walk(v, key ? `${key}.${k}` : k)
    } else if (value != null) out[key] = String(value)
  }
  walk(body, '')
  return out
}

export function Field({
  label,
  htmlFor,
  error,
  required,
  help,
  className,
  children,
}: {
  label: string
  htmlFor?: string
  error?: string
  required?: boolean
  help?: string
  className?: string
  children: ReactNode
}) {
  return (
    <div className={cn('min-w-0', className)}>
      <label htmlFor={htmlFor} className="mb-1.5 block field-label">
        {label}
        {required ? <span className="text-danger"> *</span> : null}
      </label>
      {children}
      {help ? <p className="mt-1 text-xs text-ink-muted">{help}</p> : null}
      {error ? <p className="mt-1 text-sm text-danger">{error}</p> : null}
    </div>
  )
}

/** `null` for an empty picker / date, the number otherwise. */
export function idOrNull(value: string): number | null {
  return value ? Number(value) : null
}

export function orNull(value: string): string | null {
  return value ? value : null
}

export function today(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

export function shiftDate(iso: string, days: number): string {
  const [y, m, d] = iso.split('-').map(Number)
  const date = new Date(y, m - 1, d + days)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export const PRIORITY_TONE = { low: 'muted', medium: 'info', high: 'warning', critical: 'danger' } as const

export const STATUS_TONE = {
  new: 'info',
  in_progress: 'brand',
  done: 'success',
  overdue: 'danger',
  postponed: 'muted',
  escalated: 'warning',
} as const
