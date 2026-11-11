import type { ReactNode } from 'react'

import { useI18n } from '@/i18n'

export function Field({ id, label, error, optional, children, className }: { id: string; label: string; error?: string; optional?: boolean; children: ReactNode; className?: string }) {
  const { t } = useI18n()
  return (
    <div className={className}>
      <label htmlFor={id} className="mb-1.5 flex items-baseline justify-between gap-2 text-sm font-bold text-ink">
        {label}
        {optional ? <span className="text-xs font-medium text-muted">{t('form.optional')}</span> : null}
      </label>
      {children}
      {error ? (
        <p id={`${id}-error`} role="alert" className="mt-1.5 text-sm font-medium text-danger">{error}</p>
      ) : null}
    </div>
  )
}

/** Hidden honeypot field: bots fill it, people never see it. */
export function Honeypot({ register }: { register: object }) {
  return (
    <div aria-hidden="true" className="absolute -left-[9999px] h-0 w-0 overflow-hidden">
      <label>
        Website
        <input type="text" tabIndex={-1} autoComplete="off" {...register} />
      </label>
    </div>
  )
}
