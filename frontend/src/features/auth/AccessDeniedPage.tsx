import { ShieldAlert } from 'lucide-react'

import { Button } from '@/components/ui/Button'
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
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-surface-muted px-4 text-center">
      <span className="flex size-14 items-center justify-center rounded-full bg-warning-soft text-warning">
        <ShieldAlert className="size-6" aria-hidden />
      </span>
      <div>
        <h1 className="text-lg font-semibold text-ink">Доступ ограничен</h1>
        <p className="mt-1 max-w-sm text-sm text-ink-secondary">{reason}</p>
      </div>
      <Button variant="secondary" onClick={logout}>
        Выйти и вернуться ко входу
      </Button>
    </div>
  )
}
