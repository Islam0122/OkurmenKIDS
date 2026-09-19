import { Link } from 'react-router-dom'

import { useNewsList } from '@/hooks/useNews'

import { NewsCard } from './NewsCard'
import { NewsCardSkeleton } from './NewsCardSkeleton'
import { NewsEmptyState } from './NewsEmptyState'

const DASHBOARD_PREVIEW_COUNT = 3

/** "Новости" card on the Teacher Dashboard — the latest 3 active items, with a link to the full feed. */
export function NewsWidget() {
  const { data, isPending } = useNewsList()
  const items = (data?.results ?? []).slice(0, DASHBOARD_PREVIEW_COUNT)

  return (
    <div className="rounded-xl border border-border bg-surface p-5">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm font-medium text-ink-secondary">📢 Новости</p>
        <Link to="/app/news" className="text-sm text-brand-700 hover:underline">
          Все →
        </Link>
      </div>

      <div className="space-y-2.5">
        {isPending ? (
          <>
            <NewsCardSkeleton />
            <NewsCardSkeleton />
            <NewsCardSkeleton />
          </>
        ) : null}

        {!isPending && items.length === 0 ? <NewsEmptyState /> : null}

        {items.map((item) => (
          <NewsCard key={item.id} news={item} to={`/app/news/${item.id}`} />
        ))}
      </div>
    </div>
  )
}
