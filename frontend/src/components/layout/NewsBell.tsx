import { Bell } from 'lucide-react'
import { Link } from 'react-router-dom'

import { useUnreadNewsCount } from '@/hooks/useNews'

/** Header bell — links to the full News feed, badged with the unread count from GET /teacher/news/unread-count/. */
export function NewsBell() {
  const { data } = useUnreadNewsCount()
  const count = data?.count ?? 0

  return (
    <Link
      to="/app/news"
      aria-label={count > 0 ? `Новости — ${count} непрочитано` : 'Новости'}
      className="relative flex size-9 items-center justify-center rounded-full text-ink-muted hover:bg-surface-hover hover:text-ink"
    >
      <Bell className="size-5" aria-hidden />
      {count > 0 ? (
        <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-semibold leading-none text-white">
          {count > 99 ? '99+' : count}
        </span>
      ) : null}
    </Link>
  )
}
