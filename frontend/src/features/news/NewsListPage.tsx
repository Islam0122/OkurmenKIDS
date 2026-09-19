import { Megaphone } from 'lucide-react'

import { PageHeader } from '@/components/layout/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { cn } from '@/utils/cn'
import { useMarkNewsRead, useNewsList } from '@/hooks/useNews'
import type { News } from '@/types/news'

import { NEWS_TYPE_META, formatNewsDate } from './newsMeta'

function NewsItem({ news }: { news: News }) {
  const meta = NEWS_TYPE_META[news.type]
  const Icon = meta.icon
  const { mutate: markRead, isPending: isMarking } = useMarkNewsRead()

  function handleOpen() {
    if (!news.is_read && !isMarking) markRead(news.id)
  }

  return (
    <button
      type="button"
      onClick={handleOpen}
      className={cn(
        'w-full rounded-xl border p-5 text-left transition-colors',
        news.is_read ? 'border-border bg-surface' : 'border-brand-200 bg-brand-50/40',
      )}
    >
      <div className="flex items-start gap-3">
        <span className={`flex size-9 shrink-0 items-center justify-center rounded-full ${meta.bgClass} ${meta.iconClass}`}>
          <Icon className="size-5" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <p className={`text-xs font-semibold uppercase tracking-wide ${meta.iconClass}`}>{news.type_label}</p>
          <p className="mt-1 text-base font-semibold text-ink">{news.title}</p>
          <p className="mt-1 whitespace-pre-wrap text-sm text-ink-secondary">{news.text}</p>
          <div className="mt-3 flex items-center justify-between gap-2">
            <span className="text-xs text-ink-muted">{formatNewsDate(news.created_at)}</span>
            {news.is_read ? (
              <span className="text-xs font-medium text-brand-700">✓ Прочитано</span>
            ) : (
              <span className="text-xs font-medium text-ink-muted">Непрочитано</span>
            )}
          </div>
        </div>
      </div>
    </button>
  )
}

export function NewsListPage() {
  const { data, isPending, isError, refetch } = useNewsList()
  const items = data?.results ?? []

  return (
    <div>
      <PageHeader title="📢 Новости" description="Важные объявления от администрации." />

      {isPending ? <LoadingState label="Загружаем новости…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}

      {!isPending && !isError && items.length === 0 ? (
        <EmptyState
          icon={Megaphone}
          title="Новостей пока нет"
          description="Здесь будут отображаться важные объявления."
        />
      ) : null}

      {items.length > 0 ? (
        <div className="space-y-3">
          {items.map((item) => (
            <NewsItem key={item.id} news={item} />
          ))}
        </div>
      ) : null}
    </div>
  )
}
