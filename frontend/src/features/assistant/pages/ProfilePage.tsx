import { LogOut } from 'lucide-react'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { useAuth } from '@/hooks/useAuth'
import { ROLE_LABEL } from '@/lib/roles'

import { InfoRow } from '../ui'

/** The Assistant's own account. Roles, passwords and system settings are the Admin's (Django admin). */
export function AssistantProfilePage() {
  const { user, logout } = useAuth()
  if (!user) return null
  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="Профиль" />
      <Card>
        <dl className="divide-y divide-border">
          <InfoRow label="Имя">{`${user.first_name} ${user.last_name}`.trim()}</InfoRow>
          <InfoRow label="Логин">{user.username}</InfoRow>
          <InfoRow label="Email">{user.email}</InfoRow>
          <InfoRow label="Роль">{ROLE_LABEL[user.role]}</InfoRow>
        </dl>
        <p className="mt-4 text-sm text-ink-secondary">Изменить данные аккаунта или пароль может администратор академии.</p>
        <div className="mt-4 border-t border-border pt-4">
          <Button variant="secondary" leftIcon={<LogOut className="size-4" aria-hidden />} onClick={logout}>Выйти</Button>
        </div>
      </Card>
    </div>
  )
}
