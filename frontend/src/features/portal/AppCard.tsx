import type { MouseEvent, ReactNode } from 'react'
import { motion, type Variants } from 'framer-motion'
import { ArrowRight, ArrowUpRight, Lock } from 'lucide-react'
import { Link } from 'react-router-dom'

import { cn } from '@/utils/cn'

import { PROGRAMS, type CardState, type PortalApp } from './config'
import { useI18n } from './i18n'

export const cardVariants: Variants = {
  hidden: { opacity: 0, y: 12, scale: 0.985 },
  show: { opacity: 1, y: 0, scale: 1, transition: { type: 'spring', stiffness: 260, damping: 26 } },
}

/** Moves the soft highlight under the cursor (CSS variables, no re-render). */
function trackPointer(event: MouseEvent<HTMLElement>) {
  const rect = event.currentTarget.getBoundingClientRect()
  event.currentTarget.style.setProperty('--x', `${event.clientX - rect.left}px`)
  event.currentTarget.style.setProperty('--y', `${event.clientY - rect.top}px`)
}

const frameBase =
  'group relative flex h-full flex-col overflow-hidden rounded-2xl border p-4 text-left outline-none pd-shadow transition-[border-color,background-color,box-shadow] duration-300 hover:pd-shadow-lg focus-visible:ring-4 sm:p-5 lg:p-4 short:p-3.5'
const frameDefault = 'border-pd-line bg-pd-panel hover:border-pd-line-strong focus-visible:border-pd-green focus-visible:ring-pd-green/15'
const frameFeatured = 'border-pd-green-line bg-pd-green-soft hover:border-pd-green/50 focus-visible:border-pd-green focus-visible:ring-pd-green/20'

interface AppCardProps {
  app: PortalApp
  state: CardState
  /** 1-based keyboard shortcut. */
  shortcut: number
}

export function AppCard({ app, state, shortcut }: AppCardProps) {
  const { t } = useI18n()
  const text = t.apps[app.id]
  const frame = cn(frameBase, app.featured ? frameFeatured : frameDefault)
  const body = <CardBody app={app} state={state} shortcut={shortcut} />
  const hint = state.kind === 'login' ? ` (${t.card.signInRequired})` : state.kind === 'open' && state.external ? ` (${t.card.newTab})` : ''
  const label = `${text.name} — ${text.description ?? text.tagline}${hint}`

  let inner: ReactNode
  if (state.kind === 'open' && state.external) {
    inner = (
      <a href={state.href} target="_blank" rel="noopener noreferrer" className={frame} onMouseMove={trackPointer} aria-label={label} data-app={app.id}>
        {body}
      </a>
    )
  } else if (state.kind === 'open') {
    inner = (
      <Link to={state.href} className={frame} onMouseMove={trackPointer} aria-label={label} data-app={app.id}>
        {body}
      </Link>
    )
  } else if (state.kind === 'login') {
    inner = (
      <Link to="/login" state={{ from: { pathname: state.href, search: '' } }} className={frame} onMouseMove={trackPointer} aria-label={label} data-app={app.id}>
        {body}
      </Link>
    )
  } else {
    inner = (
      <div className={cn(frame, 'cursor-not-allowed opacity-60')} aria-disabled aria-label={`${text.name} — ${t.card.soon}`} data-app={app.id}>
        {body}
      </div>
    )
  }

  return (
    <motion.li
      variants={cardVariants}
      whileHover={state.kind === 'unavailable' ? undefined : { y: -3 }}
      whileTap={state.kind === 'unavailable' ? undefined : { scale: 0.985 }}
      transition={{ type: 'spring', stiffness: 400, damping: 30 }}
      className={cn('list-none', app.featured && 'col-span-2 md:col-span-3 lg:col-span-2')}
    >
      {inner}
    </motion.li>
  )
}

function CardBody({ app, state, shortcut }: AppCardProps) {
  const { t } = useI18n()
  const text = t.apps[app.id]
  const Icon = app.icon
  const Indicator = state.kind === 'login' ? Lock : state.kind === 'open' && state.external ? ArrowUpRight : ArrowRight

  return (
    <>
      {/* cursor highlight */}
      <span
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
        style={{ background: 'radial-gradient(240px circle at var(--x, 50%) var(--y, 0%), rgb(22 163 74 / 0.06), transparent 70%)' }}
      />

      <span className="relative flex items-start justify-between gap-3">
        <span
          className={cn(
            'grid size-10 shrink-0 place-items-center rounded-xl border transition-colors duration-300',
            app.featured
              ? 'border-pd-green-line bg-pd-panel text-pd-green'
              : 'border-pd-line bg-pd-subtle text-pd-ink group-hover:border-pd-green-line group-hover:bg-pd-green-soft group-hover:text-pd-green',
          )}
        >
          <Icon className="size-5" strokeWidth={1.75} aria-hidden />
        </span>
        <span className="flex items-center gap-2">
          <kbd className="hidden h-5 min-w-5 place-items-center rounded-md border border-pd-line bg-pd-panel px-1 font-mono text-[10px] text-pd-faint lg:grid" aria-hidden>
            {shortcut}
          </kbd>
          {state.kind === 'login' ? (
            <span className="hidden text-[10px] font-semibold uppercase tracking-wider text-pd-faint xl:inline">{t.card.signIn}</span>
          ) : null}
          {state.kind === 'unavailable' ? (
            <span className="rounded-full border border-pd-line px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-pd-faint">{t.card.soon}</span>
          ) : (
            <span
              className={cn(
                'grid size-8 place-items-center rounded-full border transition-all duration-300',
                app.featured ? 'border-pd-green/30 bg-pd-panel text-pd-green' : 'border-pd-line bg-pd-panel text-pd-faint',
                'group-hover:border-pd-green group-hover:bg-pd-green group-hover:text-white',
              )}
              aria-hidden
            >
              <Indicator
                className={cn(
                  'size-3.5 transition-transform duration-300',
                  state.kind === 'open' && !state.external && 'group-hover:translate-x-0.5',
                  state.kind === 'open' && state.external && 'group-hover:-translate-y-px group-hover:translate-x-px',
                )}
              />
            </span>
          )}
        </span>
      </span>

      <span className="relative mt-3 block min-w-0 sm:mt-3.5 short:mt-2.5">
        <span className="flex items-center gap-2">
          <span className="text-[15px] font-bold leading-tight tracking-tight sm:truncate sm:text-base">{text.name}</span>
          {app.featured ? (
            <span className="hidden rounded-full bg-pd-green px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-white sm:inline">{t.card.explore}</span>
          ) : null}
        </span>
        <span className="mt-1 line-clamp-2 block text-xs leading-snug text-pd-muted sm:text-[13px]">{text.description ?? text.tagline}</span>
      </span>

      {app.featured ? (
        <span className="relative mt-auto hidden flex-wrap gap-1.5 pt-3 sm:flex short:hidden">
          {PROGRAMS.map((program) => {
            const ProgramIcon = program.icon
            return (
              <span
                key={program.id}
                className="flex items-center gap-1.5 rounded-lg border border-pd-green-line bg-pd-panel px-2 py-1 text-[11px] font-medium text-pd-ink"
              >
                <ProgramIcon className="size-3.5 shrink-0 text-pd-green" aria-hidden />
                {t.programs[program.id].name}
              </span>
            )
          })}
        </span>
      ) : (
        <span className="relative mt-auto hidden flex-wrap gap-1.5 pt-3 sm:flex short:hidden">
          {text.features.map((feature) => (
            <span key={feature} className="rounded-md border border-pd-line bg-pd-subtle px-1.5 py-0.5 text-[11px] font-medium text-pd-muted">
              {feature}
            </span>
          ))}
        </span>
      )}
    </>
  )
}
