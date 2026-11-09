import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { LoadingState } from '@/components/ui/LoadingState'
import { OfflinePage } from '@/features/auth/OfflinePage'
import { useAuth } from '@/hooks/useAuth'
import { PORTAL_PATH } from '@/lib/appMode'

/**
 * Gates every `/app/*` route. The backend remains the source of truth for
 * every permission decision this makes here — this only decides what the UI
 * shows first; every data request still goes through the real API, which
 * enforces role/ownership itself regardless of what this component renders.
 */
export function ProtectedRoute() {
  const { status, retry, signedOut } = useAuth()
  const location = useLocation()

  if (status === 'loading') {
    return <LoadingState label="Проверяем сессию…" fullScreen />
  }

  if (status === 'offline') {
    return <OfflinePage onRetry={retry} />
  }

  if (status === 'guest') {
    // «Выйти» → the public portal, the front door of the platform. A visitor
    // or an expired session → /login, then back to this very page.
    if (signedOut) return <Navigate to={PORTAL_PATH} replace />
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  if (status === 'forbidden') {
    return <Navigate to="/access-denied" replace />
  }

  return <Outlet />
}
