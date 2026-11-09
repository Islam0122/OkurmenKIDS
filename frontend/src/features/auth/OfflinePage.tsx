import { useEffect, useRef } from 'react'
import { WifiOff } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { FullScreenStatus } from '@/components/ui/FullScreenStatus'
import { BRAND } from '@/lib/brand'
import { usePwaState } from '@/pwa/store'
import { cn } from '@/utils/cn'

export interface OfflinePageProps {
  onRetry: () => void
}

/** Retry by itself every so often while the device reports a connection —
 * the server may be the one that was down. */
const AUTO_RETRY_MS = 30_000

/** Shown when the app can't reach the backend at all (down, or the network dropped) — deliberately distinct from "guest": we never throw away a possibly-valid session over a connectivity blip. Recovers on its own once the connection returns. */
export function OfflinePage({ onRetry }: OfflinePageProps) {
  const { online } = usePwaState()
  const wasOffline = useRef(!online)

  useEffect(() => {
    if (!online) {
      wasOffline.current = true
      return
    }
    if (wasOffline.current) {
      wasOffline.current = false
      onRetry()
      return
    }
    const timer = window.setInterval(onRetry, AUTO_RETRY_MS)
    return () => window.clearInterval(timer)
  }, [online, onRetry])

  return (
    <FullScreenStatus
      icon={WifiOff}
      tone="warning"
      title="Сервер недоступен"
      description={
        <>
          {`Не удалось связаться с сервером ${BRAND.name}. Проверьте подключение к интернету и попробуйте ещё раз.`}
          <span
            role="status"
            className={cn(
              'mx-auto mt-4 flex w-fit items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold',
              online ? 'bg-brand-50 text-brand-700' : 'bg-warning-soft text-warning',
            )}
          >
            <span className="size-2 animate-pulse rounded-full bg-current" aria-hidden />
            {online ? 'Интернет есть — ждём ответа сервера' : 'Нет подключения к интернету'}
          </span>
        </>
      }
      actions={
        <Button variant="secondary" onClick={onRetry}>
          Повторить подключение
        </Button>
      }
    />
  )
}
