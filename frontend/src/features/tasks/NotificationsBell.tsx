import { useState } from 'react'
import { Bell, CheckCheck } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { Drawer } from '@/components/ui/Drawer'
import { EmptyState } from '@/components/ui/EmptyState'
import { useNotificationMutations, useNotifications, useUnreadNotifications } from '@/hooks/useOperations'
import { cn } from '@/utils/cn'

/** Уведомления сотрудника (backend: /api/v1/notifications/ — только свои):
 * новая задача, дедлайн, возврат и подтверждение, отчёт, KPI, проблема. */
export function NotificationsBell() {
  const [open, setOpen] = useState(false)
  const unread = useUnreadNotifications()
  const list = useNotifications({})
  const { read, readAll } = useNotificationMutations()
  const navigate = useNavigate()
  const count = unread.data?.count ?? 0

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={count ? `Уведомления: ${count} новых` : 'Уведомления'}
        className="relative flex size-10 items-center justify-center rounded-lg text-ink-secondary hover:bg-surface-hover hover:text-ink"
      >
        <Bell className="size-5" aria-hidden />
        {count ? (
          <span className="absolute right-1 top-1 flex min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-semibold leading-4 text-white">
            {count > 99 ? '99+' : count}
          </span>
        ) : null}
      </button>
      <Drawer isOpen={open} onClose={() => setOpen(false)} title="Уведомления" side="right">
        <div className="space-y-3">
          {count ? (
            <button type="button" onClick={() => readAll.mutate()} className="inline-flex items-center gap-1.5 text-sm font-medium text-brand-700 hover:underline">
              <CheckCheck className="size-4" aria-hidden /> Отметить все прочитанными
            </button>
          ) : null}
          {list.data && list.data.results.length === 0 ? <EmptyState title="Уведомлений нет" /> : null}
          <ul className="space-y-1">
            {(list.data?.results ?? []).map((n) => (
              <li key={n.id}>
                <button
                  type="button"
                  onClick={() => {
                    if (!n.is_read) read.mutate(n.id)
                    if (n.link) {
                      setOpen(false)
                      navigate(n.link)
                    }
                  }}
                  className={cn('w-full rounded-lg border px-3 py-2 text-left transition-colors hover:bg-surface-hover', n.is_read ? 'border-transparent' : 'border-brand-200 bg-brand-50/40')}
                >
                  <span className="block text-xs text-ink-muted">{n.kind_label} · {new Date(n.created_at).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })}</span>
                  <span className="block text-sm font-medium text-ink">{n.title}</span>
                  {n.message ? <span className="mt-0.5 line-clamp-2 block text-xs text-ink-secondary">{n.message}</span> : null}
                </button>
              </li>
            ))}
          </ul>
        </div>
      </Drawer>
    </>
  )
}
