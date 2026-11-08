import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

/** Empty / no-results / error / not-found block in the portal style. */
export function StatusBlock({ icon: Icon, title, text, action, tone = 'neutral' }: { icon: LucideIcon; title: string; text: string; action?: ReactNode; tone?: 'neutral' | 'danger' }) {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center rounded-2xl border border-dashed border-pd-line-strong bg-pd-panel/80 px-6 py-12 text-center" role={tone === 'danger' ? 'alert' : 'status'}>
      <span className={tone === 'danger' ? 'grid size-12 place-items-center rounded-2xl bg-red-50 text-red-600' : 'grid size-12 place-items-center rounded-2xl border border-pd-green-line bg-pd-green-soft text-pd-green'}>
        <Icon className="size-6" strokeWidth={1.75} aria-hidden />
      </span>
      <h2 className="mt-4 text-base font-bold tracking-tight">{title}</h2>
      <p className="mt-1 text-sm text-pd-muted">{text}</p>
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  )
}

export const buttonPrimary =
  'inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-pd-green px-4 text-sm font-semibold text-white pd-shadow transition hover:bg-pd-green-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-pd-green disabled:opacity-60'
export const buttonSecondary =
  'inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-pd-line bg-pd-panel px-4 text-sm font-semibold text-pd-ink pd-shadow transition hover:border-pd-green-line hover:text-pd-green focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-pd-green'
