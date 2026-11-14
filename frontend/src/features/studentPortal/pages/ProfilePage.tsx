import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { KeyRound, LogOut } from 'lucide-react'

import { studentPortalApi } from '@/api/studentPortal'
import { useAuth } from '@/hooks/useAuth'
import { extractErrorMessage } from '@/lib/apiError'
import { cn } from '@/utils/cn'

import { PORTAL_KEY, usePortal } from '../context'
import { usePortalI18n } from '../i18n'
import type { Lang } from '../i18n'
import { Avatar, PCard, PageTitle } from '../ui'

const INPUT = 'h-11 w-full rounded-xl border border-border bg-surface px-3 text-sm text-ink focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100'

/** Used for the forced first-login change and for a later change from the profile. */
export function ChangePasswordForm({ onDone }: { onDone?: () => void }) {
  const { t } = usePortalI18n()
  const queryClient = useQueryClient()
  const [form, setForm] = useState({ current_password: '', new_password: '', new_password_confirm: '' })
  const [done, setDone] = useState(false)
  const mismatch = form.new_password_confirm !== '' && form.new_password !== form.new_password_confirm
  const mutation = useMutation({
    mutationFn: () => studentPortalApi.changePassword(form),
    onSuccess: async () => {
      setDone(true)
      setForm({ current_password: '', new_password: '', new_password_confirm: '' })
      await queryClient.invalidateQueries({ queryKey: PORTAL_KEY })
      onDone?.()
    },
  })
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => { setDone(false); setForm((f) => ({ ...f, [key]: e.target.value })) }
  return (
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (!mismatch) mutation.mutate() }}>
      {([
        ['current_password', 'pwd.current', 'current-password'],
        ['new_password', 'pwd.new', 'new-password'],
        ['new_password_confirm', 'pwd.confirm', 'new-password'],
      ] as const).map(([key, label, autoComplete]) => (
        <div key={key}>
          <label htmlFor={`pwd-${key}`} className="mb-1 block text-sm font-medium text-ink">{t(label)}</label>
          <input id={`pwd-${key}`} type="password" autoComplete={autoComplete} required value={form[key]} onChange={set(key)} className={INPUT} />
        </div>
      ))}
      <p className="text-xs text-ink-muted">{t('pwd.hint')}</p>
      {mismatch ? <p className="text-sm text-danger">{t('pwd.mismatch')}</p> : null}
      {mutation.error ? <p className="text-sm text-danger">{extractErrorMessage(mutation.error)}</p> : null}
      {done ? <p className="text-sm font-medium text-brand-700">{t('pwd.done')}</p> : null}
      <button type="submit" disabled={mutation.isPending || mismatch || !form.current_password || !form.new_password}
        className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-brand-500 text-sm font-semibold text-white hover:bg-brand-600 disabled:opacity-50">
        <KeyRound className="size-4" aria-hidden />{t('pwd.submit')}
      </button>
    </form>
  )
}

export function StudentProfilePage() {
  const { me, student, selectStudent } = usePortal()
  const { t, lang, setLang, date } = usePortalI18n()
  const { logout } = useAuth()
  return (
    <div className="mx-auto max-w-3xl">
      <PageTitle title={t('profile.title')} />
      <div className="space-y-5">
        <PCard title={t('profile.children')}>
          <ul className="space-y-2">
            {me.students.map((child) => (
              <li key={child.id}>
                <button type="button" onClick={() => selectStudent(child.id)}
                  className={cn('flex w-full items-center gap-3 rounded-xl border p-3 text-left', child.id === student.id ? 'border-brand-200 bg-brand-50/60' : 'border-border/70 hover:bg-surface-hover')}>
                  <Avatar student={child} />
                  <span className="min-w-0 flex-1">
                    <span className="block font-semibold text-ink">{child.full_name}</span>
                    <span className="block text-xs text-ink-secondary">
                      {[child.group?.name, child.course?.name, child.branch ? (lang === 'ky' && child.branch.name_ky ? child.branch.name_ky : child.branch.name) : null].filter(Boolean).join(' · ')}
                    </span>
                    <span className="block text-xs text-ink-muted">
                      {child.birth_date ? `${t('profile.birth')}: ${date(child.birth_date, true)} · ` : ''}
                      {child.enrollment_date ? `${t('profile.start')}: ${date(child.enrollment_date, true)}` : ''}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </PCard>
        <PCard title={t('profile.language')}>
          <div className="flex gap-2">
            {([['ru', 'Русский'], ['ky', 'Кыргызча']] as [Lang, string][]).map(([code, name]) => (
              <button key={code} type="button" onClick={() => setLang(code)} aria-pressed={lang === code}
                className={cn('rounded-xl px-4 py-2 text-sm font-medium ring-1', lang === code ? 'bg-brand-500 text-white ring-brand-500' : 'text-ink-secondary ring-border')}>
                {name}
              </button>
            ))}
          </div>
        </PCard>
        <PCard title={t('pwd.changeTitle')}>
          <p className="mb-3 text-sm text-ink-secondary">{t('profile.login')}: <b className="font-mono text-ink">{me.login}</b></p>
          <div className="max-w-sm"><ChangePasswordForm /></div>
        </PCard>
        <button type="button" onClick={logout} className="inline-flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium text-ink-secondary hover:bg-surface hover:text-ink lg:hidden">
          <LogOut className="size-4" aria-hidden />{t('nav.logout')}
        </button>
      </div>
    </div>
  )
}
