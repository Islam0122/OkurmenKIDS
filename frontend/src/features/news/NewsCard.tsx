import { Link } from 'react-router-dom'

import { cn } from '@/utils/cn'
import type { News } from '@/types/news'

import { AUDIENCE_META, NEWS_TYPE_META, formatNewsTimestamp, isRedundantNewsText } from './newsMeta'

export interface NewsCardProps {
  news: News
  to: string
}

/** One News item as a compact, self-contained card — used on both the
 * Dashboard widget and the full feed, always linking through (marking as
 * read happens on the detail page itself, once it's actually opened). */
export function NewsCard({ news, to }: NewsCardProps) {
  const typeMeta = NEWS_TYPE_META[news.type]
  const TypeIcon = typeMeta.icon
  const AudienceIcon = AUDIENCE_META[news.audience].icon
  const showText = !isRedundantNewsText(news.title, news.text)

  return (
    <Link
      to={to}
      className={cn(
        'block rounded-2xl border p-4 transition-all duration-150 hover:-translate-y-px hover:shadow-sm',
        news.is_read ? 'border-border bg-surface' : 'border-brand-200 bg-brand-50/30',
      )}
    >
      <div className="flex gap-3">
        <span
          className={cn(
            'flex size-10 shrink-0 items-center justify-center rounded-xl sm:size-11',
            typeMeta.bgClass,
            typeMeta.iconClass,
          )}
        >
          <TypeIcon className="size-5" aria-hidden />
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <span className={cn('text-xs font-semibold uppercase tracking-wide', typeMeta.iconClass)}>
              {news.type_label}
            </span>
            <span className="shrink-0 text-xs text-ink-muted">{formatNewsTimestamp(news.created_at)}</span>
          </div>

          <p className={cn('mt-1 truncate text-sm sm:text-base', news.is_read ? 'font-medium text-ink-secondary' : 'font-semibold text-ink')}>
            {news.title}
          </p>

          {showText ? <p className="mt-0.5 line-clamp-2 text-sm text-ink-secondary">{news.text}</p> : null}

          <div className="mt-2.5 flex items-center justify-between gap-2">
            <span className="flex items-center gap-1 text-xs text-ink-muted">
              <AudienceIcon className="size-3.5" aria-hidden />
              {news.audience_label}
            </span>

            {news.is_read ? (
              <span className="text-xs font-medium text-brand-700">✓ Прочитано</span>
            ) : (
              <span className="flex items-center gap-1 text-xs font-medium text-danger">
                <span className="size-1.5 rounded-full bg-danger" aria-hidden />
                Новое
              </span>
            )}
          </div>
        </div>
      </div>
    </Link>
  )
}
