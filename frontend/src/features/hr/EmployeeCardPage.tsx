import { useState } from 'react'
import { KeyRound, PencilLine, Power } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'

import { BackLink } from '@/components/ui/BackLink'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { useHrEmployee, useHrMeta } from '@/hooks/useHrEmployees'
import { extractErrorMessage } from '@/lib/apiError'

import { EmployeeForm, formatDate, PasswordForm, ToggleActiveDialog } from './EmployeesPage'
import { ActivityList, officeDateTime } from './shared'

/** /hr/employees/:id — карточка сотрудника: только данные, которые есть в
 * системе, история кадровых действий и кандидат, из которого он принят. */
export function HrEmployeeCardPage() {
  const id = Number(useParams().id)
  const card = useHrEmployee(id)
  const meta = useHrMeta()
  const [dialog, setDialog] = useState<'edit' | 'password' | 'toggle' | null>(null)

  if (card.isPending) return <LoadingState label="Загружаем карточку…" />
  if (card.isError) return <ErrorState title="Карточка недоступна" message={extractErrorMessage(card.error)} onRetry={() => void card.refetch()} />
  const e = card.data

  const rows: [string, string][] = [
    ['Логин', e.username],
    ['Email', e.email],
    ['Должность', e.role_label],
    ['Учётная запись создана', formatDate(e.created_at)],
    ['Последний вход', e.last_login ? officeDateTime(e.last_login) : 'ещё не входил'],
  ]

  return (
    <div className="space-y-5">
      <BackLink to="/hr/employees">Сотрудники</BackLink>
      <Card>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold text-ink sm:text-2xl">{e.full_name}</h1>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <Badge tone={e.is_active ? 'success' : 'muted'}>{e.is_active ? 'Активен' : 'Деактивирован'}</Badge>
              <span className="text-sm text-ink-secondary">{e.role_label}</span>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" leftIcon={<PencilLine className="size-4" aria-hidden />} onClick={() => setDialog('edit')}>Изменить</Button>
            <Button size="sm" variant="secondary" leftIcon={<KeyRound className="size-4" aria-hidden />} onClick={() => setDialog('password')}>Пароль</Button>
            <Button size="sm" variant={e.is_active ? 'ghost' : 'secondary'} leftIcon={<Power className="size-4" aria-hidden />} onClick={() => setDialog('toggle')}>
              {e.is_active ? 'Деактивировать' : 'Активировать'}
            </Button>
          </div>
        </div>
        <dl className="mt-5 grid gap-3 sm:grid-cols-2">
          {rows.map(([label, value]) => (
            <div key={label}>
              <dt className="text-xs uppercase tracking-wide text-ink-muted">{label}</dt>
              <dd className="break-words text-sm text-ink">{value}</dd>
            </div>
          ))}
          {e.hired_from ? (
            <div>
              <dt className="text-xs uppercase tracking-wide text-ink-muted">Принят из кандидатов</dt>
              <dd className="text-sm">
                <Link className="text-brand-700 hover:underline" to={`/hr/candidates/${e.hired_from.id}?application=${e.hired_from.application}`}>{e.hired_from.full_name}</Link>
                {e.hired_from.position ? <span className="text-ink-secondary"> · {e.hired_from.position}</span> : null}
              </dd>
            </div>
          ) : null}
        </dl>
      </Card>
      <Card title="История кадровых действий">
        <ActivityList items={e.history} showSubject={false} empty="Действий с учётной записью через HR-кабинет ещё не было." />
      </Card>

      <Modal isOpen={dialog === 'edit'} onClose={() => setDialog(null)} title="Изменить сотрудника">
        {dialog === 'edit' ? <EmployeeForm employee={e} roles={meta.data?.roles ?? []} onClose={() => setDialog(null)} /> : null}
      </Modal>
      <Modal isOpen={dialog === 'password'} onClose={() => setDialog(null)} title="Новый пароль">
        {dialog === 'password' ? <PasswordForm employee={e} onClose={() => setDialog(null)} /> : null}
      </Modal>
      <ToggleActiveDialog employee={dialog === 'toggle' ? e : null} onClose={() => setDialog(null)} />
    </div>
  )
}
