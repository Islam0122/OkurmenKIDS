import { Megaphone } from 'lucide-react'
import { Link } from 'react-router-dom'

import { EmptyState } from '@/components/ui/EmptyState'
import { LoadingState } from '@/components/ui/LoadingState'
import { useNewsList } from '@/hooks/useNews'

import { NEWS_TYPE_META, formatNewsTimestamp } from './newsMeta'

const DASHBOARD_PREVIEW_COUNT = 5

/** "Новости" card on the Teacher Dashboard — the latest few active items, with a link to the full feed. */
export function NewsWidget() {
  const { data, isPending } = useNewsList()
  const items = (data?.results ?? []).slice(0, DASHBOARD_PREVIEW_COUNT)

  return (
    <div className="rounded-xl border border-border bg-surface p-5">
      <div className="mb-3 flex items-center justify-between">
        <p className="flex items-center gap-2 text-sm font-medium text-ink-secondary">
          <Megaphone className="size-4" aria-hidden />
          Новости
        </p>
        <Link to="/app/news" className="text-sm text-brand-700 hover:underline">
          Все →
        </Link>
      </div>

      {isPending ? <LoadingState label="Загружаем новости…" /> : null}

      {!isPending && items.length === 0 ? (
        <EmptyState
          icon={Megaphone}
          title="Новостей пока нет"
          description="Здесь будут отображаться важные объявления."
        />
      ) : null}

      {items.length > 0 ? (
        <ol className="divide-y divide-border">
          {items.map((item) => {
            const meta = NEWS_TYPE_META[item.type]
            const Icon = meta.icon
            return (
              <li key={item.id}>
                <Link to="/app/news" className="flex items-start gap-3 py-3 first:pt-0 last:pb-0 hover:bg-surface-hover">
                  <span className={`flex size-8 shrink-0 items-center justify-center rounded-full ${meta.bgClass} ${meta.iconClass}`}>
                    <Icon className="size-4" aria-hidden />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium text-ink">{item.title}</span>
                      {!item.is_read ? <span className="size-1.5 shrink-0 rounded-full bg-danger" aria-label="Непрочитано" /> : null}
                    </span>
                    <span className="mt-0.5 block truncate text-xs text-ink-secondary">{item.text}</span>
                    <span className="mt-0.5 block text-xs text-ink-muted">{formatNewsTimestamp(item.created_at)}</span>
                  </span>
                </Link>
              </li>
            )
          })}
        </ol>
      ) : null}
    </div>
  )
}
