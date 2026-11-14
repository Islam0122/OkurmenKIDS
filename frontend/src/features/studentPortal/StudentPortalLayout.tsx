import { useState } from 'react'
import type { ReactNode } from 'react'
import { BarChart3, CalendarDays, ChevronDown, ClipboardList, CreditCard, GraduationCap, Home, LogOut, UserRound, UserCheck } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'

import { useAuth } from '@/hooks/useAuth'
import { cn } from '@/utils/cn'

import { PortalProvider, usePortal, usePortalMe } from './context'
import { PortalI18nProvider, usePortalI18n } from './i18n'
import type { Lang } from './i18n'
import { ChangePasswordForm } from './pages/ProfilePage'
import { Avatar, LoadError, Loading } from './ui'

/**
 * Кабинет ученика и родителя (/student). Desktop: a sidebar with the child
 * switcher; phone: a compact top bar and a bottom navigation. Until the
 * temporary password is replaced, only the password form is shown (the
 * backend refuses every data request meanwhile — apps.portal.access).
 */

const NAV = [
  { to: '/student', end: true, key: 'nav.home', icon: Home },
  { to: '/student/schedule', key: 'nav.schedule', icon: CalendarDays },
  { to: '/student/homework', key: 'nav.homework', icon: ClipboardList },
  { to: '/student/attendance', key: 'nav.attendance', icon: UserCheck },
  { to: '/student/reports', key: 'nav.reports', icon: BarChart3 },
  { to: '/student/payments', key: 'nav.payments', icon: CreditCard, payments: true },
  { to: '/student/profile', key: 'nav.profile', icon: UserRound },
] as const

const BOTTOM = ['/student', '/student/schedule', '/student/homework', '/student/reports', '/student/profile']

function LangSwitch({ className }: { className?: string }) {
  const { lang, setLang } = usePortalI18n()
  return (
    <div className={cn('inline-flex rounded-lg bg-surface-muted p-0.5 text-xs font-semibold', className)} role="group" aria-label="Язык / Тил">
      {(['ru', 'ky'] as Lang[]).map((code) => (
        <button key={code} type="button" onClick={() => setLang(code)} aria-pressed={lang === code}
          className={cn('rounded-md px-2 py-1 uppercase', lang === code ? 'bg-surface text-brand-700 shadow-sm' : 'text-ink-secondary')}>
          {code === 'ru' ? 'RU' : 'KG'}
        </button>
      ))}
    </div>
  )
}

function ChildSwitcher({ compact = false }: { compact?: boolean }) {
  const { me, student, selectStudent } = usePortal()
  const { t } = usePortalI18n()
  const [open, setOpen] = useState(false)
  const many = me.students.length > 1
  return (
    <div className="relative">
      <button type="button" disabled={!many} onClick={() => setOpen((v) => !v)} aria-expanded={open} aria-haspopup="listbox"
        aria-label={`${t('switcher.label')}: ${student.full_name}`}
        className={cn('flex w-full items-center gap-2.5 rounded-xl text-left', compact ? 'p-1' : 'border border-border/70 p-2.5', many && 'hover:bg-surface-hover')}>
        <Avatar student={student} size={compact ? 'sm' : 'md'} />
        {!compact ? (
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-semibold text-ink">{student.full_name}</span>
            <span className="block truncate text-xs text-ink-secondary">{student.group?.name ?? '—'}</span>
          </span>
        ) : null}
        {many ? <ChevronDown className="size-4 shrink-0 text-ink-muted" aria-hidden /> : null}
      </button>
      {open ? (
        <ul role="listbox" className={cn('absolute z-40 mt-1 w-64 overflow-hidden rounded-xl border border-border bg-surface p-1 shadow-xl', compact ? 'right-0' : 'left-0')}>
          {me.students.map((child) => (
            <li key={child.id}>
              <button type="button" role="option" aria-selected={child.id === student.id}
                onClick={() => { selectStudent(child.id); setOpen(false) }}
                className={cn('flex w-full items-center gap-2.5 rounded-lg p-2 text-left hover:bg-surface-hover', child.id === student.id && 'bg-brand-50')}>
                <Avatar student={child} size="sm" />
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium text-ink">{child.full_name}</span>
                  <span className="block truncate text-xs text-ink-secondary">{child.group?.name ?? '—'}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

function Shell() {
  const { me, student } = usePortal()
  const { t } = usePortalI18n()
  const { logout } = useAuth()
  const items = NAV.filter((item) => !('payments' in item) || me.can_view_payments)
  return (
    <div className="min-h-dvh bg-surface-muted/60">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-border/70 bg-surface px-4 py-5 lg:flex">
        <div className="mb-5 flex items-center gap-2 px-1">
          <span className="flex size-9 items-center justify-center rounded-xl bg-brand-500 text-white"><GraduationCap className="size-5" aria-hidden /></span>
          <span className="leading-tight">
            <span className="block text-sm font-bold text-ink">OkurmenKIDS</span>
            <span className="block text-xs text-ink-secondary">{t('brand.portal')}</span>
          </span>
        </div>
        <ChildSwitcher />
        <nav className="mt-5 flex-1 space-y-0.5" aria-label={t('brand.portal')}>
          {items.map((item) => (
            <NavLink key={item.to} to={item.to} end={'end' in item}
              className={({ isActive }) => cn('flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors',
                isActive ? 'bg-brand-50 text-brand-700' : 'text-ink-secondary hover:bg-surface-hover hover:text-ink')}>
              <item.icon className="size-[18px]" aria-hidden />{t(item.key)}
            </NavLink>
          ))}
        </nav>
        <div className="flex items-center justify-between gap-2 border-t border-border/70 pt-4">
          <LangSwitch />
          <button type="button" onClick={logout} className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm text-ink-secondary hover:bg-surface-hover hover:text-ink">
            <LogOut className="size-4" aria-hidden />{t('nav.logout')}
          </button>
        </div>
      </aside>

      {/* Phone top bar */}
      <header className="sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-border/70 bg-surface/95 px-4 py-2.5 backdrop-blur lg:hidden">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-brand-500 text-white"><GraduationCap className="size-4" aria-hidden /></span>
          <span className="truncate text-sm font-semibold text-ink">{student.first_name}</span>
        </div>
        <div className="flex items-center gap-2">
          <LangSwitch />
          <ChildSwitcher compact />
        </div>
      </header>

      <main className="px-4 pb-28 pt-5 sm:px-6 lg:ml-64 lg:px-10 lg:pb-12 lg:pt-8">
        <div className="mx-auto max-w-6xl">
          <Outlet key={student.id} />
        </div>
      </main>

      {/* Phone bottom navigation */}
      <nav className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-border/70 bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden"
        aria-label={t('brand.portal')}>
        {items.filter((item) => BOTTOM.includes(item.to)).map((item) => (
          <NavLink key={item.to} to={item.to} end={'end' in item}
            className={({ isActive }) => cn('flex flex-col items-center gap-0.5 py-2 text-[11px] font-medium', isActive ? 'text-brand-600' : 'text-ink-muted')}>
            <item.icon className="size-5" aria-hidden />{t(item.key)}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}

function Gate({ children }: { children?: ReactNode }) {
  const { data: me, isPending, isError, refetch } = usePortalMe()
  const { t } = usePortalI18n()
  const { logout } = useAuth()
  if (isPending) return <Loading />
  if (isError || !me) return <LoadError onRetry={() => void refetch()} />
  if (me.must_change_password) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-surface-muted/60 px-4 py-10">
        <div className="w-full max-w-md rounded-2xl border border-border/70 bg-surface p-6 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <span className="flex size-10 items-center justify-center rounded-xl bg-brand-500 text-white"><GraduationCap className="size-5" aria-hidden /></span>
            <LangSwitch />
          </div>
          <h1 className="text-xl font-bold text-ink">{t('pwd.title')}</h1>
          <p className="mb-5 mt-1 text-sm text-ink-secondary">{t('pwd.subtitle')}</p>
          <ChangePasswordForm onDone={() => void refetch()} />
          <button type="button" onClick={logout} className="mt-4 text-sm text-ink-secondary hover:text-ink">{t('nav.logout')}</button>
        </div>
      </div>
    )
  }
  if (me.students.length === 0) return <LoadError onRetry={() => void refetch()} />
  return <PortalProvider me={me}>{children ?? <Shell />}</PortalProvider>
}

export function StudentPortalLayout() {
  return (
    <PortalI18nProvider>
      <Gate />
    </PortalI18nProvider>
  )
}
