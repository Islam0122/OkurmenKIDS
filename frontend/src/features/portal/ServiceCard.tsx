import type { ReactNode } from 'react'
import { motion } from 'framer-motion'
import { ArrowRight, ArrowUpRight, Clock3, Lock } from 'lucide-react'
import { Link } from 'react-router-dom'

import { cn } from '@/utils/cn'

import { cardVariants } from './AppCard'
import type { CardState, PortalService } from './config'
import { useI18n } from './i18n'

const frame =
  'group flex h-full items-center gap-3 rounded-xl border border-pd-line bg-pd-panel px-3.5 py-3 text-left outline-none pd-shadow transition-[border-color,box-shadow,background-color] duration-300 hover:border-pd-green-line hover:pd-shadow-lg focus-visible:border-pd-green focus-visible:ring-4 focus-visible:ring-pd-green/15 short:py-2.5'

/** A compact «More from Okurmen» card: icon, title, one line of text, arrow. */
export function ServiceCard({ service, state }: { service: PortalService; state: CardState }) {
  const { t } = useI18n()
  const text = t.services[service.id]
  const Icon = service.icon
  const opensNewTab = state.kind === 'open' && state.external
  const Indicator = state.kind === 'login' ? Lock : opensNewTab ? ArrowUpRight : ArrowRight
  const hint = state.kind === 'login' ? ` (${t.card.signInRequired})` : opensNewTab ? ` (${t.card.newTab})` : ''
  const label = `${text.name} — ${text.description}${hint}`

  const body = (
    <>
      <span className="grid size-9 shrink-0 place-items-center rounded-lg border border-pd-line bg-pd-subtle text-pd-ink transition-colors duration-300 group-hover:border-pd-green-line group-hover:bg-pd-green-soft group-hover:text-pd-green">
        <Icon className="size-[18px]" strokeWidth={1.75} aria-hidden />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-bold tracking-tight" title={text.name}>
          {text.name}
        </span>
        <span className="line-clamp-2 block text-xs leading-snug text-pd-muted sm:line-clamp-1 lg:line-clamp-2 short:line-clamp-1">{text.description}</span>
      </span>
      {state.kind === 'unavailable' ? (
        <span className="grid size-7 shrink-0 place-items-center rounded-full border border-dashed border-pd-line-strong text-pd-faint" title={t.card.soon} aria-hidden>
          <Clock3 className="size-3.5" />
        </span>
      ) : (
        <span
          className="grid size-7 shrink-0 place-items-center rounded-full border border-pd-line text-pd-faint transition-all duration-300 group-hover:border-pd-green group-hover:bg-pd-green group-hover:text-white"
          aria-hidden
        >
          <Indicator
            className={cn(
              'size-3.5 transition-transform duration-300',
              state.kind === 'open' && !opensNewTab && 'group-hover:translate-x-0.5',
              opensNewTab && 'group-hover:-translate-y-px group-hover:translate-x-px',
            )}
          />
        </span>
      )}
    </>
  )

  let inner: ReactNode
  if (state.kind === 'open' && state.external && /^https?:\/\//i.test(state.href)) {
    inner = (
      <a href={state.href} target="_blank" rel="noopener noreferrer" className={frame} aria-label={label} data-service={service.id}>
        {body}
      </a>
    )
  } else if (state.kind === 'open') {
    inner = (
      <Link
        to={state.href}
        target={state.external ? '_blank' : undefined}
        rel={state.external ? 'noopener noreferrer' : undefined}
        className={frame}
        aria-label={label}
        data-service={service.id}
      >
        {body}
      </Link>
    )
  } else if (state.kind === 'login') {
    inner = (
      <Link to="/login" state={{ from: { pathname: state.href, search: '' } }} className={frame} aria-label={label} data-service={service.id}>
        {body}
      </Link>
    )
  } else {
    inner = (
      <div className={cn(frame, 'cursor-default opacity-70 hover:border-pd-line hover:pd-shadow')} aria-disabled aria-label={`${text.name} — ${t.card.soon}`} data-service={service.id}>
        {body}
      </div>
    )
  }

  return (
    <motion.li
      variants={cardVariants}
      whileHover={state.kind === 'unavailable' ? undefined : { y: -2 }}
      whileTap={state.kind === 'unavailable' ? undefined : { scale: 0.985 }}
      transition={{ type: 'spring', stiffness: 400, damping: 30 }}
      className="min-w-0 list-none"
    >
      {inner}
    </motion.li>
  )
}
