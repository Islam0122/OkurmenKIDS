import { useEffect, useRef } from 'react'
import { AlertOctagon, WifiOff } from 'lucide-react'
import { isRouteErrorResponse, useNavigate, useRouteError } from 'react-router-dom'

import { Button } from '@/components/ui/Button'
import { FullScreenStatus } from '@/components/ui/FullScreenStatus'
import { usePwaState } from '@/pwa/store'

import { NotFoundPage } from './NotFoundPage'

/** The browser could not download a page's code (a lazy route chunk). */
function isChunkLoadError(error: unknown): boolean {
  return (
    error instanceof Error &&
    /dynamically imported module|Importing a module script failed|error loading dynamically imported module/i.test(error.message)
  )
}

/**
 * Catches anything React Router itself surfaces as a route error — a
 * component that throws while rendering, or a loader/action failure —
 * so a bug in one page never falls through to a blank tab or the
 * framework's own unstyled error screen. A thrown 404 Response (none of
 * our routes raise one today, but a future loader might) still gets the
 * dedicated 404 page instead of this generic one.
 *
 * Offline, a section that was never opened on this device has no cached
 * code: that gets its own honest message and reopens by itself once the
 * connection returns.
 */
export function RouteErrorPage() {
  const error = useRouteError()
  const navigate = useNavigate()
  const { online } = usePwaState()
  const chunkError = isChunkLoadError(error)
  const wasOffline = useRef(!online)

  useEffect(() => {
    if (!online) {
      wasOffline.current = true
      return
    }
    if (!chunkError || !wasOffline.current) return
    // Wait until the connection is stable: a flapping link fires «online»
    // spuriously, and a reload must not race a navigation the user started.
    const timer = window.setTimeout(() => {
      if (navigator.onLine) window.location.reload()
    }, 1500)
    return () => window.clearTimeout(timer)
  }, [online, chunkError])

  if (import.meta.env.DEV) {
    console.error('Route error boundary caught:', error)
  }

  if (isRouteErrorResponse(error) && error.status === 404) {
    return <NotFoundPage />
  }

  if (chunkError && !online) {
    return (
      <FullScreenStatus
        icon={WifiOff}
        tone="warning"
        title="Раздел недоступен без интернета"
        description="Этот раздел ещё не открывался на этом устройстве, поэтому офлайн его не загрузить. Он откроется сам, когда подключение вернётся."
        actions={
          <Button variant="secondary" onClick={() => navigate(0)}>
            Повторить подключение
          </Button>
        }
      />
    )
  }

  return (
    <FullScreenStatus
      icon={AlertOctagon}
      tone="danger"
      title="Что-то пошло не так"
      description="Произошла непредвиденная ошибка. Мы уже записали её — попробуйте обновить страницу."
      actions={
        <>
          <Button variant="secondary" onClick={() => navigate(0)}>
            Обновить страницу
          </Button>
          <Button onClick={() => navigate('/app/dashboard', { replace: true })}>На главную</Button>
        </>
      }
    />
  )
}
