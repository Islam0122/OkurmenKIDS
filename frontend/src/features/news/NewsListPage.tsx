import { useMemo, useState } from 'react'

import { PageHeader } from '@/components/layout/PageHeader'
import { ErrorState } from '@/components/ui/ErrorState'
import { cn } from '@/utils/cn'
import { useNewsList } from '@/hooks/useNews'

import { NewsCard } from './NewsCard'
import { NewsCardSkeleton } from './NewsCardSkeleton'
import { NewsEmptyState } from './NewsEmptyState'

type NewsFilter = 'all' | 'unread'

export function NewsListPage() {
  const [filter, setFilter] = useState<NewsFilter>('all')
  const { data, isPending, isError, refetch } = useNewsList()
  const items = data?.results ?? []

  const unreadCount = useMemo(() => items.filter((item) => !item.is_read).length, [items])
  const visibleItems = filter === 'unread' ? items.filter((item) => !item.is_read) : items

  return (
    <div>
      <PageHeader title="📢 Новости" description="Важные объявления от администрации." />

      {!isPending && !isError && items.length > 0 ? (
        <div className="mb-5 flex gap-2">
          <button
            type="button"
            onClick={() => setFilter('all')}
            className={cn(
              'rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors',
              filter === 'all' ? 'border-brand-500 bg-brand-50 text-brand-700' : 'border-border text-ink-secondary hover:bg-surface-hover',
            )}
          >
            Все · {items.length}
          </button>
          <button
            type="button"
            onClick={() => setFilter('unread')}
            className={cn(
              'rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors',
              filter === 'unread' ? 'border-brand-500 bg-brand-50 text-brand-700' : 'border-border text-ink-secondary hover:bg-surface-hover',
            )}
          >
            Непрочитанные · {unreadCount}
          </button>
        </div>
      ) : null}

      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}

      <div className="space-y-3">
        {isPending ? (
          <>
            <NewsCardSkeleton />
            <NewsCardSkeleton />
            <NewsCardSkeleton />
          </>
        ) : null}

        {!isPending && !isError && items.length === 0 ? <NewsEmptyState /> : null}

        {!isPending && !isError && items.length > 0 && visibleItems.length === 0 ? (
          <p className="py-8 text-center text-sm text-ink-secondary">Непрочитанных новостей нет.</p>
        ) : null}

        {visibleItems.map((item) => (
          <NewsCard key={item.id} news={item} to={`/app/news/${item.id}`} />
        ))}
      </div>
    </div>
  )
}
