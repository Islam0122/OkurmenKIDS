import { useState } from 'react'
import { Check, Copy, CreditCard, KeyRound, Link2, Pencil, Power, ShieldAlert, Unlink, UserRoundPlus } from 'lucide-react'
import { format } from 'date-fns'

import { assistantApi } from '@/api/assistant'
import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { useAssistantFormMutation, useAssistantMutation } from '@/hooks/useAssistant'
import { extractErrorMessage } from '@/lib/apiError'
import type { AccountStatus, IssuedCredentials, StudentDetail } from '@/types/assistant'

import { Field, FormError } from '../ui'

/**
 * Кабинет ученика и родителя (backend: apps.portal) in the Assistant
 * Workspace: the one-time credentials card, and the account panel of a
 * student's page (status, reset password, change login, on / off, payments
 * visibility, family links). The password is only ever held in component
 * state right after the server issued it — it is never fetched again.
 */

export const ACCOUNT_STATUS: Record<AccountStatus, { label: string; tone: BadgeTone }> = {
  pending: { label: 'Ждёт первого входа', tone: 'warning' },
  active: { label: 'Активен', tone: 'success' },
  disabled: { label: 'Отключён', tone: 'danger' },
}

export function AccountStatusBadge({ status }: { status: AccountStatus | null | undefined }) {
  if (!status) return <Badge tone="muted">Нет кабинета</Badge>
  return <Badge tone={ACCOUNT_STATUS[status].tone}>{ACCOUNT_STATUS[status].label}</Badge>
}

const PORTAL_URL = `${window.location.origin}/login`

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

function CopyButton({ value, label }: { value: string; label: string }) {
  const [done, setDone] = useState(false)
  return (
    <Button
      type="button"
      size="sm"
      variant="secondary"
      onClick={async () => {
        if (await copyText(value)) {
          setDone(true)
          window.setTimeout(() => setDone(false), 1800)
        }
      }}
      leftIcon={done ? <Check className="size-4" aria-hidden /> : <Copy className="size-4" aria-hidden />}
    >
      {done ? 'Скопировано' : label}
    </Button>
  )
}

/** Shown once, right after the account was created or its password reset. */
export function CredentialsCard({ credentials, studentName }: { credentials: IssuedCredentials; studentName: string }) {
  const all = [
    `Кабинет ученика OkurmenKIDS — ${studentName}`,
    `Адрес: ${PORTAL_URL}`,
    `Логин: ${credentials.login}`,
    `Временный пароль: ${credentials.password}`,
    'При первом входе нужно придумать свой пароль.',
  ].join('\n')
  return (
    <div className="rounded-xl border border-brand-200 bg-brand-50/60 p-4 text-left">
      <div className="mb-3 flex items-start gap-2 text-sm text-brand-700">
        <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
        <p>
          Данные для входа показываются <b>только один раз</b>. Передайте их семье сейчас — позже пароль можно только
          сбросить.
        </p>
      </div>
      <dl className="grid gap-2">
        {[
          ['Логин', credentials.login],
          ['Временный пароль', credentials.password],
        ].map(([label, value]) => (
          <div key={label} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-surface px-3 py-2 ring-1 ring-border">
            <div className="min-w-0">
              <dt className="text-xs text-ink-secondary">{label}</dt>
              <dd className="font-mono text-base font-semibold tracking-wide text-ink" data-testid={`cred-${label}`}>{value}</dd>
            </div>
            <CopyButton value={value} label="Копировать" />
          </div>
        ))}
      </dl>
      <div className="mt-3 flex justify-end">
        <CopyButton value={all} label="Копировать всё" />
      </div>
    </div>
  )
}

function fmt(value: string | null | undefined, pattern = 'dd.MM.yyyy HH:mm') {
  return value ? format(new Date(value), pattern) : '—'
}

export function StudentAccountPanel({ student }: { student: StudentDetail }) {
  const account = student.account
  const [credentials, setCredentials] = useState<IssuedCredentials | null>(null)
  const [confirm, setConfirm] = useState<null | 'reset' | 'toggle' | 'unlink'>(null)
  const [loginOpen, setLoginOpen] = useState(false)
  const [login, setLogin] = useState('')
  const [family, setFamily] = useState('')

  const keep = (result: StudentDetail) => {
    if (result.credentials) setCredentials(result.credentials)
  }
  const provision = useAssistantMutation(() => assistantApi.provisionAccount(student.id), 'Кабинет создан')
  const reset = useAssistantMutation(() => assistantApi.resetPassword(student.id), 'Пароль сброшен')
  const toggle = useAssistantMutation(
    () => assistantApi.setAccountActive(student.id, !account?.is_active),
    account?.is_active ? 'Вход в кабинет отключён' : 'Вход в кабинет включён',
  )
  const payments = useAssistantMutation(
    () => assistantApi.setPaymentsVisible(student.id, !account?.can_view_payments),
    'Сохранено',
  )
  const unlink = useAssistantMutation(() => assistantApi.unlinkAccount(student.id), 'Студент отвязан от кабинета')
  const link = useAssistantMutation((id: number) => assistantApi.linkAccount(student.id, id), 'Студент привязан к кабинету семьи')
  const rename = useAssistantFormMutation(() => assistantApi.changeLogin(student.id, login.trim()), 'Логин изменён')

  return (
    <Card title="Кабинет ученика и родителя" description="Вход для ученика и родителей: расписание, ДЗ, посещаемость, отчёты.">
      {credentials ? (
        <div className="mb-4">
          <CredentialsCard credentials={credentials} studentName={student.full_name} />
        </div>
      ) : null}

      {!account ? (
        <div className="space-y-3">
          <p className="text-sm text-ink-secondary">У студента ещё нет кабинета.</p>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              leftIcon={<UserRoundPlus className="size-4" aria-hidden />}
              isLoading={provision.isPending}
              onClick={() => provision.mutate(undefined, { onSuccess: keep })}
            >
              Создать кабинет
            </Button>
          </div>
          {student.family_accounts.length ? (
            <div className="rounded-lg border border-border p-3">
              <p className="mb-2 text-sm font-medium text-ink">Кабинет семьи с тем же телефоном родителя</p>
              <div className="flex flex-wrap items-end gap-2">
                <Select
                  aria-label="Кабинет семьи"
                  value={family}
                  onChange={(event) => setFamily(event.target.value)}
                  placeholder="Выберите кабинет"
                  options={student.family_accounts.map((a) => ({ value: String(a.id), label: `${a.login} · ${a.students.join(', ')}` }))}
                />
                <Button size="sm" variant="secondary" disabled={!family} isLoading={link.isPending}
                  leftIcon={<Link2 className="size-4" aria-hidden />} onClick={() => link.mutate(Number(family))}>
                  Привязать
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      ) : (
        <div className="space-y-4">
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-ink-secondary">Логин</dt>
              <dd className="flex items-center gap-2 font-mono font-semibold text-ink">
                {account.login}
                <button type="button" className="rounded p-1 text-ink-muted hover:bg-surface-hover hover:text-ink"
                  aria-label="Изменить логин" onClick={() => { setLogin(account.login); rename.reset(); setLoginOpen(true) }}>
                  <Pencil className="size-3.5" aria-hidden />
                </button>
              </dd>
            </div>
            <div>
              <dt className="text-ink-secondary">Статус</dt>
              <dd><AccountStatusBadge status={account.status} /></dd>
            </div>
            <div>
              <dt className="text-ink-secondary">Данные выданы</dt>
              <dd className="text-ink">{fmt(account.credentials_issued_at)}</dd>
            </div>
            <div>
              <dt className="text-ink-secondary">Последний вход</dt>
              <dd className="text-ink">{fmt(account.last_login)}</dd>
            </div>
            {account.students.length > 1 ? (
              <div className="sm:col-span-2">
                <dt className="text-ink-secondary">Дети в кабинете</dt>
                <dd className="text-ink">{account.students.map((s) => s.name).join(', ')}</dd>
              </div>
            ) : null}
          </dl>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" leftIcon={<KeyRound className="size-4" aria-hidden />} onClick={() => setConfirm('reset')}>
              Сбросить пароль
            </Button>
            <Button size="sm" variant="secondary" leftIcon={<Power className="size-4" aria-hidden />} onClick={() => setConfirm('toggle')}>
              {account.is_active ? 'Отключить вход' : 'Включить вход'}
            </Button>
            <Button size="sm" variant="secondary" leftIcon={<CreditCard className="size-4" aria-hidden />}
              isLoading={payments.isPending} onClick={() => payments.mutate(undefined)}>
              {account.can_view_payments ? 'Скрыть оплату' : 'Показать оплату'}
            </Button>
            {account.students.length > 1 ? (
              <Button size="sm" variant="ghost" leftIcon={<Unlink className="size-4" aria-hidden />} onClick={() => setConfirm('unlink')}>
                Отвязать от кабинета
              </Button>
            ) : null}
          </div>
        </div>
      )}

      <ConfirmDialog
        isOpen={confirm === 'reset'}
        title="Сбросить пароль?"
        message="Текущий пароль перестанет работать. Новый временный пароль будет показан один раз; при входе его нужно будет сменить."
        confirmLabel="Сбросить"
        isLoading={reset.isPending}
        onCancel={() => setConfirm(null)}
        onConfirm={() => reset.mutate(undefined, { onSuccess: (r) => { keep(r); setConfirm(null) } })}
      />
      <ConfirmDialog
        isOpen={confirm === 'toggle'}
        title={account?.is_active ? 'Отключить вход в кабинет?' : 'Включить вход в кабинет?'}
        message={account?.is_active ? 'Семья не сможет войти, пока вход не включат снова. Данные студента не удаляются.' : 'Семья снова сможет входить с прежним логином и паролем.'}
        tone={account?.is_active ? 'danger' : 'primary'}
        confirmLabel={account?.is_active ? 'Отключить' : 'Включить'}
        isLoading={toggle.isPending}
        onCancel={() => setConfirm(null)}
        onConfirm={() => toggle.mutate(undefined, { onSuccess: () => setConfirm(null) })}
      />
      <ConfirmDialog
        isOpen={confirm === 'unlink'}
        title="Отвязать студента от кабинета семьи?"
        message="Студент пропадёт из кабинета семьи. Остальные дети останутся."
        tone="danger"
        confirmLabel="Отвязать"
        isLoading={unlink.isPending}
        onCancel={() => setConfirm(null)}
        onConfirm={() => unlink.mutate(undefined, { onSuccess: () => setConfirm(null) })}
      />
      <Modal isOpen={loginOpen} onClose={() => setLoginOpen(false)} title="Изменить логин">
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            rename.mutate(undefined, { onSuccess: () => setLoginOpen(false) })
          }}
        >
          <Field label="Логин" htmlFor="account-login" hint="Латиница, цифры, точка, дефис; 3–40 символов. Пароль не меняется.">
            <Input id="account-login" value={login} onChange={(event) => setLogin(event.target.value.toLowerCase())} maxLength={40} autoFocus />
          </Field>
          <FormError message={rename.error ? extractErrorMessage(rename.error) : null} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setLoginOpen(false)}>Отмена</Button>
            <Button type="submit" disabled={login.trim().length < 3} isLoading={rename.isPending}>Сохранить</Button>
          </div>
        </form>
      </Modal>
    </Card>
  )
}
