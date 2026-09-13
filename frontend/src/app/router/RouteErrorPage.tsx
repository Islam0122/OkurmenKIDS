import { AlertOctagon } from 'lucide-react'
import { isRouteErrorResponse, useNavigate, useRouteError } from 'react-router-dom'

import { Button } from '@/components/ui/Button'
import { FullScreenStatus } from '@/components/ui/FullScreenStatus'

import { NotFoundPage } from './NotFoundPage'

/**
 * Catches anything React Router itself surfaces as a route error — a
 * component that throws while rendering, or a loader/action failure —
 * so a bug in one page never falls through to a blank tab or the
 * framework's own unstyled error screen. A thrown 404 Response (none of
 * our routes raise one today, but a future loader might) still gets the
 * dedicated 404 page instead of this generic one.
 */
export function RouteErrorPage() {
  const error = useRouteError()
  const navigate = useNavigate()

  if (import.meta.env.DEV) {
    console.error('Route error boundary caught:', error)
  }

  if (isRouteErrorResponse(error) && error.status === 404) {
    return <NotFoundPage />
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
