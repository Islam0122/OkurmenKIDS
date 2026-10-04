import { Navigate, Outlet } from 'react-router-dom'

import { useAuth } from '@/hooks/useAuth'
import type { UserRole } from '@/types/auth'

/** Hides a section from roles that have no access to it. UI only — the
 * backend refuses the data to those roles anyway (403). */
export function RequireRoles({ roles }: { roles: UserRole[] }) {
  const { user } = useAuth()
  if (!user || !roles.includes(user.role)) return <Navigate to="/app/dashboard" replace />
  return <Outlet />
}
