import { AlertTriangle, Inbox, RefreshCw, SearchX } from 'lucide-react'

import { useI18n, type MessageKey } from '@/i18n'
import { ApiError } from '@/services/api/client'
import { cn } from '@/utils/cn'

import { Button, ButtonLink } from './Button'

export function errorMessageKey(error: unknown): MessageKey {
  if (error instanceof ApiError) {
    if (error.kind === 'network') return 'state.error.network'
    if (error.kind === 'config') return 'state.error.config'
    if (error.kind === 'rate_limited') return 'state.error.rate'
  }
  return 'state.error.server'
}

export function ErrorState({ error, onRetry, className }: { error: unknown; onRetry?: () => void; className?: string }) {
  const { t } = useI18n()
  return (
    <div role="alert" className={cn('card mx-auto flex max-w-lg flex-col items-center gap-4 p-8 text-center', className)}>
      <span className="grid size-14 place-items-center rounded-2xl bg-orange-50 text-danger">
        <AlertTriangle className="size-7" aria-hidden />
      </span>
      <div>
        <p className="font-display text-lg font-extrabold">{t('state.error.title')}</p>
        <p className="mt-1 text-sm text-muted">{t(errorMessageKey(error))}</p>
      </div>
      {onRetry ? (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RefreshCw className="size-4" aria-hidden /> {t('cta.retry')}
        </Button>
      ) : null}
    </div>
  )
}

export function EmptyState({ search, className }: { search?: boolean; className?: string }) {
  const { t } = useI18n()
  const Icon = search ? SearchX : Inbox
  return (
    <div className={cn('mx-auto flex max-w-md flex-col items-center gap-3 rounded-(--radius-card) border border-dashed border-line bg-surface-soft p-10 text-center', className)}>
      <Icon className="size-9 text-brand-300" aria-hidden />
      <p className="text-muted">{t(search ? 'state.emptySearch' : 'state.empty')}</p>
    </div>
  )
}

export function NotFoundState() {
  const { t } = useI18n()
  return (
    <div className="container-page section flex flex-col items-center text-center">
      <p className="font-display text-7xl font-black text-brand-100 sm:text-9xl">404</p>
      <h1 className="mt-2 text-3xl font-extrabold">{t('state.notFound.title')}</h1>
      <p className="mt-3 max-w-md text-muted">{t('state.notFound.text')}</p>
      <ButtonLink to="/" className="mt-8">{t('cta.home')}</ButtonLink>
    </div>
  )
}

/** Card-shaped placeholders while data loads (keeps the layout stable). */
export function CardSkeletons({ count = 3, className, aspect = 'aspect-[16/10]' }: { count?: number; className?: string; aspect?: string }) {
  const { t } = useI18n()
  return (
    <div className={cn('grid gap-6 sm:grid-cols-2 lg:grid-cols-3', className)} aria-busy="true" aria-label={t('state.loading')}>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="card overflow-hidden">
          <div className={cn('animate-pulse bg-brand-50', aspect)} />
          <div className="space-y-3 p-6">
            <div className="h-3 w-1/3 animate-pulse rounded bg-brand-50" />
            <div className="h-5 w-4/5 animate-pulse rounded bg-brand-50" />
            <div className="h-3 w-full animate-pulse rounded bg-surface-soft" />
          </div>
        </div>
      ))}
    </div>
  )
}

export function PageSkeleton() {
  const { t } = useI18n()
  return (
    <div className="container-page section" aria-busy="true" aria-label={t('state.loading')}>
      <div className="h-4 w-32 animate-pulse rounded bg-brand-50" />
      <div className="mt-6 h-10 w-3/4 animate-pulse rounded-xl bg-brand-50" />
      <div className="mt-4 h-5 w-1/2 animate-pulse rounded bg-surface-soft" />
      <div className="mt-10 aspect-[16/7] animate-pulse rounded-(--radius-card) bg-brand-50" />
    </div>
  )
}
