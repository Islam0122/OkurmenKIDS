import { Navigate } from 'react-router-dom'

import { useAuth } from '@/hooks/useAuth'

/** `/my-salary` → «Моя зарплата» в кабинете своей роли. */
export function MySalaryRedirect() {
  const { user } = useAuth()
  const target = {
    assistant: '/assistant/my-salary',
    team_lead: '/app/my-salary',
    teacher: '/app/my-salary',
  }[user?.role ?? ''] ?? '/app/dashboard'
  return <Navigate to={target} replace />
}
