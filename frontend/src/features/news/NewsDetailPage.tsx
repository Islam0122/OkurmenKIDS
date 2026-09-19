import { useEffect, useRef } from 'react'
import { useParams } from 'react-router-dom'

import { BackLink } from '@/components/ui/BackLink'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { cn } from '@/utils/cn'
import { useMarkNewsRead, useNewsDetail } from '@/hooks/useNews'

import { AUDIENCE_META, NEWS_TYPE_META, formatNewsTimestamp, isRedundantNewsText } from './newsMeta'

export function NewsDetailPage() {
  const { id } = useParams<{ id: string }>()
  const newsId = Number(id)

  const { data: news, isPending, isError, refetch } = useNewsDetail(newsId)
  const { mutate: markRead } = useMarkNewsRead()

  // Marks as read exactly once per page visit, the moment the News has
  // actually loaded — never on the list card itself (see NewsCard), only
  // once this detail page is truly opened, per spec.
  const hasMarkedRead = useRef(false)
  useEffect(() => {
    if (news && !news.is_read && !hasMarkedRead.current) {
      hasMarkedRead.current = true
      markRead(news.id)
    }
  }, [news, markRead])

  if (isPending) return <LoadingState label="Загружаем новость…" />
  if (isError || !news) return <ErrorState onRetry={() => void refetch()} />

  const typeMeta = NEWS_TYPE_META[news.type]
  const TypeIcon = typeMeta.icon
  const AudienceIcon = AUDIENCE_META[news.audience].icon
  const showText = !isRedundantNewsText(news.title, news.text)

  return (
    <div>
      <BackLink to="/app/news">К новостям</BackLink>

      <div className="rounded-2xl border border-border bg-surface p-5 sm:p-6">
        <div className="flex items-center gap-2.5">
          <span className={cn('flex size-9 items-center justify-center rounded-xl', typeMeta.bgClass, typeMeta.iconClass)}>
            <TypeIcon className="size-5" aria-hidden />
          </span>
          <span className={cn('text-sm font-semibold uppercase tracking-wide', typeMeta.iconClass)}>{news.type_label}</span>
        </div>

        <h1 className="mt-4 text-xl font-semibold text-ink sm:text-2xl">{news.title}</h1>

        {showText ? <p className="mt-2 whitespace-pre-wrap text-sm text-ink-secondary sm:text-base">{news.text}</p> : null}

        <p className="mt-4 text-sm text-ink-muted">{formatNewsTimestamp(news.created_at)}</p>

        <div className="mt-4 flex flex-wrap items-center gap-4 border-t border-border pt-4">
          <span className="flex items-center gap-1.5 text-sm text-ink-secondary">
            <AudienceIcon className="size-4" aria-hidden />
            {news.audience_label}
          </span>

          {news.is_read ? (
            <span className="text-sm font-medium text-brand-700">✓ Прочитано</span>
          ) : (
            <span className="flex items-center gap-1.5 text-sm font-medium text-danger">
              <span className="size-1.5 rounded-full bg-danger" aria-hidden />
              Новое
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
