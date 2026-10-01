import { ArrowRight, Megaphone } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Card } from '@/components/ui/Card'

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
    <Card
      title={
        <span className="flex items-center gap-2">
          <Megaphone className="size-5 text-brand-600" aria-hidden />
          Новости
        </span>
      }
      actions={
        <Link to="/app/news" className="inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:underline">
          Все
          <ArrowRight className="size-4" aria-hidden />
        </Link>
      }
    >

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
    </Card>
  )
}
