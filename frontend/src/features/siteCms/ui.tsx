import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { ArrowLeft } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Badge, type BadgeTone } from '@/components/ui/Badge'
import { cn } from '@/utils/cn'

import { LANGS, STATE_LABEL, type Lang } from './schema'

/**
 * Общие элементы рабочего пространства «Управление сайтом»: заголовок
 * страницы, карточки-панели, статусы, skeleton-загрузка, переключатель
 * языков. Один визуальный язык для всех разделов CMS.
 */

export const STATE_TONE: Record<string, BadgeTone> = {
  draft: 'muted',
  review: 'warning',
  scheduled: 'info',
  published: 'success',
  archived: 'muted',
}

const STATE_CLASS: Record<string, string> = {
  published: 'bg-emerald-50 text-emerald-700',
}

/** Workflow status (the Badge draws its own dot in the text color). */
export function StatusBadge({ state, className }: { state?: string | null; className?: string }) {
  if (!state) return null
  return (
    <Badge tone={STATE_TONE[state] ?? 'muted'} className={cn('whitespace-nowrap', STATE_CLASS[state], className)}>
      {STATE_LABEL[state] ?? state}
    </Badge>
  )
}

/** Puts the brand theme (purple / yellow) on <html> while the CMS is open — portals included. */
export function useCmsTheme() {
  useEffect(() => {
    document.documentElement.classList.add('cms-theme')
    return () => document.documentElement.classList.remove('cms-theme')
  }, [])
}

export function CmsPage({ title, description, actions, back, children, eyebrow }: {
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  back?: { to: string; label: string }
  eyebrow?: ReactNode
  children: ReactNode
}) {
  return (
    <div className="space-y-5">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          {back ? (
            <Link to={back.to} className="mb-1.5 inline-flex items-center gap-1 text-sm font-medium text-ink-secondary hover:text-brand-600">
              <ArrowLeft className="size-4" aria-hidden /> {back.label}
            </Link>
          ) : null}
          {eyebrow ? <div className="mb-1">{eyebrow}</div> : null}
          <h1 className="font-display text-2xl font-bold tracking-tight text-ink sm:text-[1.75rem]">{title}</h1>
          {description ? <p className="mt-1 max-w-2xl text-sm text-ink-secondary">{description}</p> : null}
        </div>
        {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
      </header>
      {children}
    </div>
  )
}

export function Panel({ title, description, actions, children, className, bodyClassName, id }: {
  title?: ReactNode
  description?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
  id?: string
}) {
  return (
    <section id={id} className={cn('min-w-0 rounded-2xl border border-border bg-surface shadow-[0_1px_2px_rgba(28,21,51,0.04)]', className)}>
      {title || actions ? (
        <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3 sm:px-5">
          <div className="min-w-0">
            {title ? <h2 className="text-[0.9375rem] font-semibold text-ink">{title}</h2> : null}
            {description ? <p className="mt-0.5 text-xs text-ink-secondary">{description}</p> : null}
          </div>
          {actions ? <div className="flex shrink-0 items-center gap-1">{actions}</div> : null}
        </div>
      ) : null}
      <div className={cn('p-4 sm:p-5', bodyClassName)}>{children}</div>
    </section>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <span className={cn('block animate-pulse rounded-md bg-surface-hover', className)} aria-hidden />
}

/** Skeleton rows for lists and tables while data is loading. */
export function ListSkeleton({ rows = 6, thumb = true }: { rows?: number; thumb?: boolean }) {
  return (
    <div className="divide-y divide-border overflow-hidden rounded-2xl border border-border bg-surface" role="status" aria-label="Загрузка">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-3 px-4 py-3">
          {thumb ? <Skeleton className="size-11 shrink-0 rounded-lg" /> : null}
          <div className="flex-1 space-y-2">
            <Skeleton className="h-3.5 w-1/2" />
            <Skeleton className="h-3 w-1/3" />
          </div>
          <Skeleton className="hidden h-6 w-20 rounded-full sm:block" />
        </div>
      ))}
    </div>
  )
}

export function CardsSkeleton({ count = 4, className }: { count?: number; className?: string }) {
  return (
    <div className={cn('grid gap-3 sm:grid-cols-2 lg:grid-cols-4', className)} role="status" aria-label="Загрузка">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="space-y-3 rounded-2xl border border-border bg-surface p-4">
          <Skeleton className="size-9 rounded-xl" />
          <Skeleton className="h-6 w-16" />
          <Skeleton className="h-3 w-24" />
        </div>
      ))}
    </div>
  )
}

/** RU / KG / EN switch. A dot shows which languages are filled in. */
export function LangTabs({ value, onChange, filled, className }: {
  value: Lang
  onChange: (lang: Lang) => void
  filled?: Partial<Record<Lang, 'full' | 'partial' | 'empty'>>
  className?: string
}) {
  return (
    <div role="tablist" aria-label="Язык контента" className={cn('inline-flex rounded-xl border border-border bg-surface-muted p-1', className)}
      onKeyDown={(e) => {
        if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return
        const index = LANGS.findIndex((l) => l.code === value)
        const next = LANGS[(index + (e.key === 'ArrowRight' ? 1 : LANGS.length - 1)) % LANGS.length]
        onChange(next.code)
        e.preventDefault()
        ;(e.currentTarget.querySelector(`[data-lang="${next.code}"]`) as HTMLElement | null)?.focus()
      }}>
      {LANGS.map((lang) => {
        const state = filled?.[lang.code]
        const active = value === lang.code
        return (
          <button key={lang.code} type="button" role="tab" data-lang={lang.code} aria-selected={active} tabIndex={active ? 0 : -1}
            title={lang.name} onClick={() => onChange(lang.code)}
            className={cn('inline-flex h-8 min-w-14 items-center justify-center gap-1.5 rounded-lg px-3 text-sm font-semibold transition-colors',
              active ? 'bg-surface text-brand-600 shadow-sm' : 'text-ink-secondary hover:text-ink')}>
            {lang.label}
            {state ? (
              <span aria-label={state === 'full' ? 'заполнено' : state === 'partial' ? 'заполнено частично' : 'не заполнено'}
                className={cn('size-1.5 rounded-full', state === 'full' ? 'bg-emerald-500' : state === 'partial' ? 'bg-cms-gold' : 'bg-border-strong')} />
            ) : null}
          </button>
        )
      })}
    </div>
  )
}

export function Counter({ value, max }: { value: string; max: number }) {
  const n = value.length
  return <span className={cn('text-xs tabular-nums', n > max ? 'font-semibold text-danger' : 'text-ink-muted')}>{n} / {max}</span>
}

export function FieldLabel({ htmlFor, children, required, aside }: { htmlFor?: string; children: ReactNode; required?: boolean; aside?: ReactNode }) {
  return (
    <div className="mb-1.5 flex items-center justify-between gap-2">
      <label htmlFor={htmlFor} className="text-sm font-medium text-ink">{children}{required ? <span className="text-danger"> *</span> : null}</label>
      {aside}
    </div>
  )
}

export function Hint({ children }: { children: ReactNode }) {
  return <p className="mt-1 text-xs text-ink-muted">{children}</p>
}

const dateFmt = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' })
const dateTimeFmt = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

export function formatDate(value: unknown, withTime = false): string {
  if (!value) return ''
  const d = new Date(String(value))
  if (Number.isNaN(d.getTime())) return ''
  return (withTime ? dateTimeFmt : dateFmt).format(d)
}

/** «5 мин назад», «вчера», else a date. */
export function relativeTime(value: unknown): string {
  if (!value) return ''
  const d = new Date(String(value))
  const diff = (Date.now() - d.getTime()) / 1000
  if (Number.isNaN(diff)) return ''
  if (diff < 60) return 'только что'
  if (diff < 3600) return `${Math.floor(diff / 60)} мин назад`
  if (diff < 86_400) return `${Math.floor(diff / 3600)} ч назад`
  if (diff < 172_800) return 'вчера'
  return formatDate(d)
}

export const formatSize = (bytes: number) =>
  bytes > 1_048_576 ? `${(bytes / 1_048_576).toFixed(1)} МБ` : `${Math.max(1, Math.round(bytes / 1024))} КБ`

export const fileExt = (url: string) => (url.split('?')[0].split('.').pop() ?? '').toUpperCase().slice(0, 5)

export const CMS_BASE = '/marketing/site'
export const editorPath = (resource: string, id?: number | 'new') => `${CMS_BASE}/${resource}/${id ?? 'new'}`

/** Classes of a link styled as a button (variants match components/ui/Button). */
export const linkButton = (variant: 'primary' | 'secondary' | 'ghost' | 'gold' = 'secondary', size: 'sm' | 'md' = 'md') => cn(
  'inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-lg font-medium transition-colors',
  size === 'sm' ? 'h-8 px-3 text-sm' : 'h-10 px-4 text-sm',
  variant === 'primary' && 'bg-brand-500 text-white hover:bg-brand-600',
  variant === 'secondary' && 'border border-brand-200 bg-surface text-brand-700 hover:bg-brand-50',
  variant === 'ghost' && 'text-ink-secondary hover:bg-surface-hover',
  variant === 'gold' && 'bg-cms-gold text-brand-700 hover:brightness-95',
)

export interface DropdownItem {
  key: string
  label: string
  onClick: () => void
  icon?: ReactNode
  tone?: 'default' | 'danger'
  disabled?: boolean
  hint?: string
}

/** A dropdown with any trigger (e.g. «Создать контент»); arrows, Home/End and Escape work. */
export function Dropdown({ trigger, items, align = 'end', label, triggerClassName }: {
  trigger: ReactNode
  items: DropdownItem[]
  align?: 'start' | 'end'
  label: string
  triggerClassName?: string
}) {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const button = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!open) return
    const down = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', down)
    box.current?.querySelector<HTMLElement>('[role="menuitem"]:not([disabled])')?.focus()
    return () => document.removeEventListener('mousedown', down)
  }, [open])
  const move = (e: KeyboardEvent) => {
    const list = Array.from(box.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not([disabled])') ?? [])
    const i = list.indexOf(document.activeElement as HTMLElement)
    let next = -1
    if (e.key === 'ArrowDown') next = (i + 1) % list.length
    else if (e.key === 'ArrowUp') next = (i - 1 + list.length) % list.length
    else if (e.key === 'Home') next = 0
    else if (e.key === 'End') next = list.length - 1
    else if (e.key === 'Escape') { setOpen(false); button.current?.focus(); e.stopPropagation(); return }
    else if (e.key === 'Tab') { setOpen(false); return }
    if (next >= 0) { e.preventDefault(); list[next]?.focus() }
  }
  if (!items.length) return null
  return (
    <div ref={box} className="relative inline-block" onKeyDown={open ? move : undefined}>
      <button ref={button} type="button" aria-haspopup="menu" aria-expanded={open} aria-label={label} onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => { if (e.key === 'ArrowDown' && !open) { e.preventDefault(); setOpen(true) } }}
        className={triggerClassName ?? 'flex size-9 items-center justify-center rounded-lg border border-border bg-surface text-ink-secondary hover:bg-surface-hover'}>
        {trigger}
      </button>
      {open ? (
        <div role="menu" aria-label={label} className={cn('absolute z-30 mt-1.5 w-64 max-w-[calc(100vw-2rem)] overflow-hidden rounded-xl border border-border bg-surface py-1 shadow-lg', align === 'end' ? 'right-0' : 'left-0')}>
          {items.map((item) => (
            <button key={item.key} type="button" role="menuitem" disabled={item.disabled}
              onClick={() => { setOpen(false); item.onClick() }}
              className={cn('flex min-h-10 w-full items-center gap-2.5 px-3 py-2 text-left text-sm hover:bg-surface-hover focus:bg-surface-hover focus:outline-none disabled:cursor-not-allowed disabled:opacity-50',
                item.tone === 'danger' ? 'text-danger' : 'text-ink')}>
              {item.icon}
              <span className="min-w-0">
                <span className="block">{item.label}</span>
                {item.hint ? <span className="block text-xs text-ink-muted">{item.hint}</span> : null}
              </span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}
