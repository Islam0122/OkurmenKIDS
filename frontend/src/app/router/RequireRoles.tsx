import { Navigate, Outlet } from 'react-router-dom'

import { useAuth } from '@/hooks/useAuth'
import { isStaffOnlyRole } from '@/lib/roles'
import type { UserRole } from '@/types/auth'

/** Hides a section from roles that have no access to it. UI only — the
 * backend refuses the data to those roles anyway (403). */
export function RequireRoles({ roles, redirectTo }: { roles: UserRole[]; redirectTo?: string }) {
  const { user } = useAuth()
  if (!user || !roles.includes(user.role)) {
    const fallback = user?.role === 'accountant' ? '/accounting' : user?.role === 'hr_manager' ? '/hr' : isStaffOnlyRole(user?.role) ? '/attendance' : '/app/dashboard'
    return <Navigate to={redirectTo ?? fallback} replace />
  }
  return <Outlet />
}
