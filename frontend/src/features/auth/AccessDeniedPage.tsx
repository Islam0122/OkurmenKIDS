import { ShieldAlert } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { FullScreenStatus } from '@/components/ui/FullScreenStatus'
import { useAuth } from '@/hooks/useAuth'

export function AccessDeniedPage() {
  const { user, logout } = useAuth()

  const reason =
    user?.role !== 'teacher'
      ? 'Этот кабинет предназначен только для тренеров.'
      : !user.is_verified
        ? 'Ваш аккаунт ещё не подтверждён администратором.'
        : 'Ваш аккаунт деактивирован.'

  return (
    <FullScreenStatus
      icon={ShieldAlert}
      tone="warning"
      title="Доступ ограничен"
      description={reason}
      actions={
        <Button variant="secondary" onClick={logout}>
          Выйти и вернуться ко входу
        </Button>
      }
    />
  )
}
