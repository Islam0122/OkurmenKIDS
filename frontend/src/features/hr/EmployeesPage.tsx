import { useState, type FormEvent, type ReactNode } from 'react'
import { KeyRound, PencilLine, Plus, Power, ShieldAlert, Users } from 'lucide-react'
import { Navigate } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { useToast } from '@/components/ui/Toast'
import { useAuth } from '@/hooks/useAuth'
import {
  useHrEmployees,
  useHrMeta,
  useSaveHrEmployee,
  useSetHrEmployeeActive,
  useSetHrEmployeePassword,
} from '@/hooks/useHrEmployees'
import { extractErrorMessage } from '@/lib/apiError'
import type { HREmployee, HRRoleOption } from '@/types/hr'

const PAGE_SIZE = 20

/** /hr/employees — раздел «Сотрудники» HR-менеджера. Кого HR может менять,
 * решает сервер (apps.users.hr): защищённых сотрудников список не содержит,
 * а любое действие с ними API отклоняет. */
export function HrEmployeesPage() {
  const { user } = useAuth()
  if (user?.role !== 'hr_manager') return <Navigate to="/attendance" replace />
  return <Employees />
}

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleDateString('ru-RU') : '—'
}

function Employees() {
  const meta = useHrMeta()
  const [search, setSearch] = useState('')
  const [role, setRole] = useState('')
  const [active, setActive] = useState<'' | 'true' | 'false'>('')
  const [page, setPage] = useState(1)
  const list = useHrEmployees({ search: search.trim() || undefined, role: role || undefined, is_active: active || undefined, page })
  const [editing, setEditing] = useState<HREmployee | 'new' | null>(null)
  const [passwordFor, setPasswordFor] = useState<HREmployee | null>(null)
  const [toggling, setToggling] = useState<HREmployee | null>(null)
  const roles = meta.data?.roles ?? []

  const resetPage = <T,>(setter: (value: T) => void) => (value: T) => {
    setter(value)
    setPage(1)
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Сотрудники"
        description="Учётные записи сотрудников в ведении HR"
        actions={
          <Button leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setEditing('new')} disabled={!roles.length}>
            Новый сотрудник
          </Button>
        }
      />
      {meta.data?.protected_roles.length ? (
        <p className="flex items-start gap-2 rounded-xl bg-info-soft px-4 py-3 text-sm text-info">
          <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span>
            Учётными записями категорий {meta.data.protected_roles.map((r) => r.label).join(', ')}, руководства и
            администраторов управляет только администратор.
          </span>
        </p>
      ) : null}
      <Card>
        <div className="grid gap-3 sm:grid-cols-3">
          <SearchInput value={search} onChange={resetPage(setSearch)} placeholder="Имя, логин или email" aria-label="Поиск сотрудника" />
          <Select
            aria-label="Должность"
            value={role}
            onChange={(e) => resetPage(setRole)(e.target.value)}
            placeholder="Все должности"
            options={roles.map((r) => ({ value: r.value, label: r.label }))}
          />
          <Select
            aria-label="Статус"
            value={active}
            onChange={(e) => resetPage(setActive)(e.target.value as '' | 'true' | 'false')}
            placeholder="Все статусы"
            options={[{ value: 'true', label: 'Активные' }, { value: 'false', label: 'Деактивированные' }]}
          />
        </div>
      </Card>
      {list.isPending ? (
        <LoadingState />
      ) : list.isError ? (
        <ErrorState message={extractErrorMessage(list.error)} onRetry={() => void list.refetch()} />
      ) : list.data.results.length === 0 ? (
        <EmptyState icon={Users} title="Сотрудников не найдено" description="Измените фильтры или добавьте сотрудника." />
      ) : (
        <Card className="overflow-x-auto p-0">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="bg-surface-muted text-left text-xs uppercase tracking-wide text-ink-muted">
              <tr>
                <th scope="col" className="px-4 py-3">Сотрудник</th>
                <th scope="col" className="px-4 py-3">Должность</th>
                <th scope="col" className="px-4 py-3">Статус</th>
                <th scope="col" className="px-4 py-3">Создан</th>
                <th scope="col" className="px-4 py-3 text-right">Действия</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {list.data.results.map((employee) => (
                <tr key={employee.id}>
                  <td className="px-4 py-3">
                    <p className="font-medium text-ink">{employee.full_name}</p>
                    <p className="text-xs text-ink-secondary">{employee.username} · {employee.email}</p>
                  </td>
                  <td className="px-4 py-3">{employee.role_label}</td>
                  <td className="px-4 py-3">
                    <Badge tone={employee.is_active ? 'success' : 'muted'}>{employee.is_active ? 'Активен' : 'Деактивирован'}</Badge>
                  </td>
                  <td className="px-4 py-3 tabular-nums">{formatDate(employee.created_at)}</td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-1">
                      <Button size="sm" variant="ghost" aria-label={`Изменить ${employee.full_name}`} leftIcon={<PencilLine className="size-4" aria-hidden />} onClick={() => setEditing(employee)}>
                        Изменить
                      </Button>
                      <Button size="sm" variant="ghost" aria-label={`Пароль ${employee.full_name}`} leftIcon={<KeyRound className="size-4" aria-hidden />} onClick={() => setPasswordFor(employee)}>
                        Пароль
                      </Button>
                      <Button size="sm" variant="ghost" leftIcon={<Power className="size-4" aria-hidden />} onClick={() => setToggling(employee)}>
                        {employee.is_active ? 'Деактивировать' : 'Активировать'}
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
      {list.data ? <Pagination page={page} pageSize={PAGE_SIZE} totalCount={list.data.count} onPageChange={setPage} /> : null}

      <Modal isOpen={editing !== null} onClose={() => setEditing(null)} title={editing === 'new' ? 'Новый сотрудник' : 'Изменить сотрудника'}>
        {editing !== null ? <EmployeeForm employee={editing === 'new' ? null : editing} roles={roles} onClose={() => setEditing(null)} /> : null}
      </Modal>
      <Modal isOpen={passwordFor !== null} onClose={() => setPasswordFor(null)} title="Новый пароль">
        {passwordFor ? <PasswordForm employee={passwordFor} onClose={() => setPasswordFor(null)} /> : null}
      </Modal>
      <ToggleActiveDialog employee={toggling} onClose={() => setToggling(null)} />
    </div>
  )
}

function Field({ id, label, children }: { id: string; label: string; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block field-label">{label}</label>
      {children}
    </div>
  )
}

function FormError({ message }: { message: string | null }) {
  return message ? <p className="rounded-xl bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">{message}</p> : null
}

function EmployeeForm({ employee, roles, onClose }: { employee: HREmployee | null; roles: HRRoleOption[]; onClose: () => void }) {
  const { showToast } = useToast()
  const save = useSaveHrEmployee()
  const [form, setForm] = useState({
    username: employee?.username ?? '',
    email: employee?.email ?? '',
    first_name: employee?.first_name ?? '',
    last_name: employee?.last_name ?? '',
    role: employee?.role ?? roles[0]?.value ?? '',
    password: '',
    password_confirm: '',
  })
  const [error, setError] = useState<string | null>(null)
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }))

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    const base = {
      username: form.username.trim(),
      email: form.email.trim(),
      first_name: form.first_name.trim(),
      last_name: form.last_name.trim(),
      role: form.role as HRRoleOption['value'],
    }
    if (!employee && form.password !== form.password_confirm) {
      setError('Пароли не совпадают.')
      return
    }
    try {
      await save.mutateAsync(
        employee
          ? { id: employee.id, payload: base }
          : { payload: { ...base, password: form.password, password_confirm: form.password_confirm } },
      )
      showToast(employee ? 'Данные сотрудника сохранены' : 'Сотрудник создан', 'success')
      onClose()
    } catch (err) {
      setError(extractErrorMessage(err))
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field id="hr-first" label="Имя *"><Input id="hr-first" value={form.first_name} onChange={set('first_name')} required maxLength={100} /></Field>
        <Field id="hr-last" label="Фамилия"><Input id="hr-last" value={form.last_name} onChange={set('last_name')} maxLength={100} /></Field>
        <Field id="hr-username" label="Логин *"><Input id="hr-username" value={form.username} onChange={set('username')} required maxLength={150} autoComplete="off" /></Field>
        <Field id="hr-email" label="Email *"><Input id="hr-email" type="email" value={form.email} onChange={set('email')} required /></Field>
      </div>
      <Field id="hr-role" label="Должность *">
        <Select id="hr-role" value={form.role} onChange={set('role')} required options={roles.map((r) => ({ value: r.value, label: r.label }))} />
      </Field>
      {employee ? null : (
        <div className="grid gap-3 sm:grid-cols-2">
          <Field id="hr-password" label="Пароль *"><Input id="hr-password" type="password" value={form.password} onChange={set('password')} required autoComplete="new-password" /></Field>
          <Field id="hr-password2" label="Повторите пароль *"><Input id="hr-password2" type="password" value={form.password_confirm} onChange={set('password_confirm')} required autoComplete="new-password" /></Field>
        </div>
      )}
      <FormError message={error} />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onClose}>Отмена</Button>
        <Button type="submit" isLoading={save.isPending}>Сохранить</Button>
      </div>
    </form>
  )
}

function PasswordForm({ employee, onClose }: { employee: HREmployee; onClose: () => void }) {
  const { showToast } = useToast()
  const setPassword = useSetHrEmployeePassword()
  const [password, setPasswordValue] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    if (password !== confirm) {
      setError('Пароли не совпадают.')
      return
    }
    try {
      await setPassword.mutateAsync({ id: employee.id, password, passwordConfirm: confirm })
      showToast('Пароль изменён — передайте его сотруднику лично', 'success')
      onClose()
    } catch (err) {
      setError(extractErrorMessage(err))
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <p className="text-sm text-ink-secondary">
        Новый пароль для «{employee.full_name}». Текущий пароль не хранится и не показывается — его можно только заменить.
      </p>
      <Field id="hr-new-password" label="Новый пароль *"><Input id="hr-new-password" type="password" value={password} onChange={(e) => setPasswordValue(e.target.value)} required autoComplete="new-password" /></Field>
      <Field id="hr-new-password2" label="Повторите пароль *"><Input id="hr-new-password2" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required autoComplete="new-password" /></Field>
      <FormError message={error} />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onClose}>Отмена</Button>
        <Button type="submit" isLoading={setPassword.isPending}>Сохранить пароль</Button>
      </div>
    </form>
  )
}

function ToggleActiveDialog({ employee, onClose }: { employee: HREmployee | null; onClose: () => void }) {
  const { showToast } = useToast()
  const setActive = useSetHrEmployeeActive()
  const deactivating = employee?.is_active ?? false

  const confirm = async () => {
    if (!employee) return
    try {
      await setActive.mutateAsync({ id: employee.id, active: !employee.is_active })
      showToast(deactivating ? 'Учётная запись деактивирована' : 'Учётная запись активирована', 'success')
      onClose()
    } catch (err) {
      showToast(extractErrorMessage(err), 'error')
    }
  }

  return (
    <ConfirmDialog
      isOpen={employee !== null}
      title={deactivating ? 'Деактивировать сотрудника?' : 'Активировать сотрудника?'}
      message={
        deactivating
          ? `${employee?.full_name ?? ''} не сможет войти в систему. История посещаемости и данные сохранятся.`
          : `${employee?.full_name ?? ''} снова сможет входить в систему.`
      }
      confirmLabel={deactivating ? 'Деактивировать' : 'Активировать'}
      tone={deactivating ? 'danger' : 'primary'}
      isLoading={setActive.isPending}
      onConfirm={() => void confirm()}
      onCancel={onClose}
    />
  )
}
