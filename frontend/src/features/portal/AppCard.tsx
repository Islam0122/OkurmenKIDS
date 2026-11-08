import type { MouseEvent, ReactNode } from 'react'
import { motion, type Variants } from 'framer-motion'
import { ArrowRight, ArrowUpRight, Lock } from 'lucide-react'
import { Link } from 'react-router-dom'

import { cn } from '@/utils/cn'

import { PROGRAMS, type CardState, type PortalApp } from './config'

export const cardVariants: Variants = {
  hidden: { opacity: 0, y: 14, scale: 0.98 },
  show: { opacity: 1, y: 0, scale: 1, transition: { type: 'spring', stiffness: 260, damping: 26 } },
}

/** Moves the soft highlight under the cursor (CSS variables, no re-render). */
function trackPointer(event: MouseEvent<HTMLElement>) {
  const rect = event.currentTarget.getBoundingClientRect()
  event.currentTarget.style.setProperty('--x', `${event.clientX - rect.left}px`)
  event.currentTarget.style.setProperty('--y', `${event.clientY - rect.top}px`)
}

const frame =
  'group relative flex h-full flex-col overflow-hidden rounded-2xl border border-pd-line bg-pd-panel/90 p-4 text-left outline-none backdrop-blur-sm transition-[border-color,background-color,box-shadow] duration-300 hover:border-pd-line-strong hover:bg-pd-panel-hover hover:shadow-[0_18px_50px_-24px_rgb(74_222_128/0.35)] focus-visible:border-pd-green/70 focus-visible:ring-2 focus-visible:ring-pd-green/30 sm:p-5 lg:p-4'

interface AppCardProps {
  app: PortalApp
  state: CardState
  /** 1-based keyboard shortcut. */
  shortcut: number
}

export function AppCard({ app, state, shortcut }: AppCardProps) {
  const body = <CardBody app={app} state={state} shortcut={shortcut} />
  const label = `${app.name} — ${app.tagline}${state.kind === 'login' ? ' (sign in required)' : ''}${state.kind === 'open' && state.external ? ' (opens in a new tab)' : ''}`

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
      <Link
        to="/login"
        state={{ from: { pathname: state.href, search: '' } }}
        className={frame}
        onMouseMove={trackPointer}
        aria-label={label}
        data-app={app.id}
      >
        {body}
      </Link>
    )
  } else {
    inner = (
      <div className={cn(frame, 'cursor-not-allowed opacity-60')} aria-disabled aria-label={`${app.name} — coming soon`} data-app={app.id}>
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
  const Icon = app.icon
  const Indicator = state.kind === 'login' ? Lock : state.kind === 'open' && state.external ? ArrowUpRight : ArrowRight

  return (
    <>
      {/* cursor highlight */}
      <span
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
        style={{ background: 'radial-gradient(260px circle at var(--x, 50%) var(--y, 0%), rgb(74 222 128 / 0.07), transparent 70%)' }}
      />
      {app.featured ? (
        <span aria-hidden className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-pd-green/60 to-transparent" />
      ) : null}

      <span className="relative flex items-start justify-between gap-3">
        <span
          className={cn(
            'grid size-10 shrink-0 place-items-center rounded-xl border transition-colors duration-300 sm:size-11 lg:size-10',
            app.featured
              ? 'border-pd-green/40 bg-pd-green/10 text-pd-green'
              : 'border-pd-line bg-pd-bg text-pd-ink group-hover:border-pd-green/40 group-hover:text-pd-green',
          )}
        >
          <Icon className="size-5" strokeWidth={1.75} aria-hidden />
        </span>
        <span className="flex items-center gap-2">
          <kbd className="hidden h-5 min-w-5 place-items-center rounded border border-pd-line px-1 font-mono text-[10px] text-pd-faint lg:grid" aria-hidden>
            {shortcut}
          </kbd>
          {state.kind === 'login' ? (
            <span className="hidden text-[10px] font-medium uppercase tracking-wider text-pd-faint xl:inline">Sign in</span>
          ) : null}
          {state.kind === 'unavailable' ? (
            <span className="rounded-full border border-pd-line px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-pd-faint">Soon</span>
          ) : (
            <span
              className={cn(
                'grid size-7 place-items-center rounded-full border border-pd-line text-pd-faint transition-all duration-300',
                'group-hover:border-pd-green/50 group-hover:text-pd-green',
                state.kind === 'open' && !state.external && 'group-hover:translate-x-0.5',
                state.kind === 'open' && state.external && 'group-hover:-translate-y-0.5 group-hover:translate-x-0.5',
              )}
              aria-hidden
            >
              <Indicator className="size-3.5" />
            </span>
          )}
        </span>
      </span>

      <span className="relative mt-3 block min-w-0 sm:mt-4">
        <span className="flex items-center gap-2">
          <span className="text-[15px] font-bold leading-tight tracking-tight sm:truncate sm:text-base">{app.name}</span>
          {app.featured ? (
            <span className="hidden rounded-full bg-pd-green/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-pd-green sm:inline">Explore</span>
          ) : null}
        </span>
        <span className="mt-1 line-clamp-2 block text-xs leading-snug text-pd-muted sm:text-[13px]">{app.description ?? app.tagline}</span>
      </span>

      {app.featured ? (
        <span className="relative mt-auto hidden flex-wrap gap-2 pt-3 sm:flex">
          {PROGRAMS.map((program) => {
            const ProgramIcon = program.icon
            return (
              <span
                key={program.id}
                className="flex items-center gap-1.5 rounded-lg border border-pd-line bg-pd-bg/60 px-2 py-1.5 text-[11px] font-medium text-pd-muted transition-colors group-hover:border-pd-line-strong"
              >
                <ProgramIcon className="size-3.5 shrink-0 text-pd-green" aria-hidden />
                {program.name}
              </span>
            )
          })}
        </span>
      ) : (
        <span className="relative mt-auto hidden flex-wrap gap-1.5 pt-3 sm:flex">
          {app.features.map((feature) => (
            <span key={feature} className="rounded-md border border-pd-line bg-pd-bg/60 px-1.5 py-0.5 text-[11px] text-pd-faint transition-colors group-hover:text-pd-muted">
              {feature}
            </span>
          ))}
        </span>
      )}
    </>
  )
}
