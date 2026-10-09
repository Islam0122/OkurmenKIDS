import { Outlet } from 'react-router-dom'

import { useAuth } from '@/hooks/useAuth'
import type { UserRole } from '@/types/auth'

import { SiteNoAccess } from './SiteLayout'

/** Roles the backend lets read the academy-wide schedule (CanViewSchedule).
 * UI only — the API refuses everyone else (403) on its own. */
export const SCHEDULE_SITE_ROLES: UserRole[] = ['admin', 'team_lead', 'assistant']

export function SiteAccess() {
  const { user } = useAuth()
  if (!user || !SCHEDULE_SITE_ROLES.includes(user.role)) return <SiteNoAccess />
  return <Outlet />
}
