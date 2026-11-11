import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'

import { useI18n } from '@/i18n'
import { cn } from '@/utils/cn'

export interface Crumb {
  label: string
  to?: string
}

/** The top of every inner page: breadcrumbs, title, lead text — on a soft brand background. */
export function PageHero({ title, text, crumbs = [], children, compact, wide }: { title: ReactNode; text?: ReactNode; crumbs?: Crumb[]; children?: ReactNode; compact?: boolean; /** gallery pages: the wider content width */ wide?: boolean }) {
  const { t, path } = useI18n()
  const all: Crumb[] = [{ label: t('nav.home'), to: '/' }, ...crumbs]
  return (
    <section className="relative overflow-hidden bg-surface-purple">
      <div aria-hidden className="pointer-events-none absolute -top-24 -right-24 size-80 rounded-full bg-gold-200/50 blur-3xl" />
      <div aria-hidden className="pointer-events-none absolute -bottom-32 -left-20 size-80 rounded-full bg-brand-200/40 blur-3xl" />
      <div className={cn(wide ? 'mx-auto w-[calc(100%-48px)] max-w-[1280px]' : 'container-page', 'relative', compact ? 'pt-6 pb-8 sm:pt-8 sm:pb-10' : 'pt-8 pb-12 sm:pt-10 sm:pb-16')}>
        <nav aria-label="breadcrumb">
          <ol className="flex flex-wrap items-center gap-1 text-sm text-muted">
            {all.map((crumb, i) => (
              <li key={i} className="flex items-center gap-1">
                {i > 0 ? <ChevronRight className="size-3.5 opacity-60" aria-hidden /> : null}
                {crumb.to && i < all.length - 1 ? (
                  <Link to={path(crumb.to)} className="hover:text-brand-800">{crumb.label}</Link>
                ) : (
                  <span aria-current={i === all.length - 1 ? 'page' : undefined} className="line-clamp-1 text-ink-soft">{crumb.label}</span>
                )}
              </li>
            ))}
          </ol>
        </nav>
        <h1 className={cn('mt-5 max-w-4xl leading-[1.05] font-black', compact ? 'text-3xl sm:text-4xl lg:text-5xl' : 'text-4xl sm:text-5xl lg:text-6xl')}>{title}</h1>
        {text ? <p className={cn('max-w-2xl text-ink-soft', compact ? 'mt-3 text-base sm:text-lg' : 'mt-5 text-lg')}>{text}</p> : null}
        {children}
      </div>
    </section>
  )
}
