import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { LoadingState } from '@/components/ui/LoadingState'
import { useAuth } from '@/hooks/useAuth'

/**
 * Gates every `/app/*` route. The backend remains the source of truth for
 * every permission decision this makes here — this only decides what the UI
 * shows first; every data request still goes through the real API, which
 * enforces role/ownership itself regardless of what this component renders.
 */
export function ProtectedRoute() {
  const { status } = useAuth()
  const location = useLocation()

  if (status === 'loading') {
    return <LoadingState label="Проверяем сессию…" fullScreen />
  }

  if (status === 'guest') {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  if (status === 'forbidden') {
    return <Navigate to="/access-denied" replace />
  }

  return <Outlet />
}
