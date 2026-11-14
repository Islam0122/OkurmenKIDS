import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import {
  BarChart3, BookOpenCheck, CalendarDays, Check, ChevronDown, Home, LogOut, MoreHorizontal, Trophy, UserCheck, UserRound,
  Wallet,
} from 'lucide-react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'

import logo from '@/assets/logo.png'
import { useAuth } from '@/hooks/useAuth'
import { cn } from '@/utils/cn'

import { PortalProvider, usePortal, usePortalMe } from './context'
import { PortalI18nProvider, usePortalI18n } from './i18n'
import type { Lang } from './i18n'
import { ChangePasswordForm } from './pages/ProfilePage'
import { Avatar, LoadError, Loading } from './ui'

/**
 * Кабинет ученика и родителя (/student).
 *
 * Desktop (lg+): a fixed sidebar — compact logo, the student card (with the
 * child switcher for families with several children), icon navigation with
 * a clear active state, language switch and logout. Phone and tablet: a
 * compact top bar and a bottom navigation of the four main sections plus
 * «Дагы», a bottom sheet with the rest. Payments appear only when the
 * family's account may see them (PortalAccount.can_view_payments).
 *
 * Until the temporary password is replaced, only the password form is shown
 * (the backend refuses every data request meanwhile — apps.portal.access).
 */

type NavKey = 'nav.home' | 'nav.schedule' | 'nav.homework' | 'nav.attendance' | 'nav.reports' | 'nav.achievements' | 'nav.payments' | 'nav.profile'
interface NavItem { to: string; key: NavKey; icon: typeof Home; end?: boolean; payments?: boolean }

const NAV: NavItem[] = [
  { to: '/student', end: true, key: 'nav.home', icon: Home },
  { to: '/student/schedule', key: 'nav.schedule', icon: CalendarDays },
  { to: '/student/homework', key: 'nav.homework', icon: BookOpenCheck },
  { to: '/student/attendance', key: 'nav.attendance', icon: UserCheck },
  { to: '/student/reports', key: 'nav.reports', icon: BarChart3 },
  { to: '/student/achievements', key: 'nav.achievements', icon: Trophy },
  { to: '/student/payments', key: 'nav.payments', icon: Wallet, payments: true },
  { to: '/student/profile', key: 'nav.profile', icon: UserRound },
]

/** Phone/tablet bottom bar; everything else lives in the «Дагы» sheet. */
const BOTTOM = ['/student', '/student/schedule', '/student/homework', '/student/achievements']
const SHORT: Partial<Record<NavKey, 'nav.short.home' | 'nav.short.schedule' | 'nav.short.homework' | 'nav.short.achievements'>> = {
  'nav.home': 'nav.short.home',
  'nav.schedule': 'nav.short.schedule',
  'nav.homework': 'nav.short.homework',
  'nav.achievements': 'nav.short.achievements',
}

function LangSwitch({ className }: { className?: string }) {
  const { lang, setLang } = usePortalI18n()
  return (
    <div className={cn('inline-flex rounded-xl bg-surface-muted p-1 text-xs font-bold', className)} role="group" aria-label="Язык / Тил">
      {(['ru', 'ky'] as Lang[]).map((code) => (
        <button key={code} type="button" onClick={() => setLang(code)} aria-pressed={lang === code}
          className={cn('sp-press min-w-9 rounded-lg px-2.5 py-1.5 uppercase', lang === code ? 'bg-surface text-brand-700 shadow-sm' : 'text-ink-muted hover:text-ink')}>
          {code === 'ru' ? 'RU' : 'KG'}
        </button>
      ))}
    </div>
  )
}

function useOutsideClose(open: boolean, close: () => void) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onDown = (event: MouseEvent) => { if (!ref.current?.contains(event.target as Node)) close() }
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') close() }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey) }
  }, [open, close])
  return ref
}

/** The student card: who is shown, and — for a family with several children — the switch. */
function StudentCard({ compact = false }: { compact?: boolean }) {
  const { me, student, selectStudent } = usePortal()
  const { t } = usePortalI18n()
  const [open, setOpen] = useState(false)
  const ref = useOutsideClose(open, () => setOpen(false))
  const many = me.students.length > 1
  return (
    <div ref={ref} className="relative">
      <button type="button" disabled={!many} onClick={() => setOpen((v) => !v)} aria-expanded={open} aria-haspopup="listbox"
        aria-label={`${t('switcher.label')}: ${student.full_name}`}
        className={cn('sp-press flex w-full items-center gap-3 text-left',
          compact ? 'rounded-full p-0.5' : 'rounded-2xl bg-gradient-to-br from-brand-50 to-surface p-3 ring-1 ring-brand-100',
          many && !compact && 'hover:ring-brand-200')}>
        <Avatar student={student} size={compact ? 'sm' : 'md'} />
        {!compact ? (
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-bold text-ink">{student.full_name}</span>
            <span className="block truncate text-xs font-medium text-ink-secondary">{student.group?.name ?? '—'}{student.course ? ` · ${student.course.name}` : ''}</span>
          </span>
        ) : null}
        {many && !compact ? <ChevronDown className={cn('size-4 shrink-0 text-ink-muted transition-transform', open && 'rotate-180')} aria-hidden /> : null}
      </button>
      {open ? (
        <ul role="listbox" className={cn('sp-rise absolute z-50 mt-2 w-72 overflow-hidden rounded-2xl border border-border bg-surface p-1.5 shadow-xl', compact ? 'right-0' : 'left-0')}>
          {me.students.map((child) => (
            <li key={child.id}>
              <button type="button" role="option" aria-selected={child.id === student.id}
                onClick={() => { selectStudent(child.id); setOpen(false) }}
                className={cn('flex w-full items-center gap-3 rounded-xl p-2.5 text-left hover:bg-surface-hover', child.id === student.id && 'bg-brand-50')}>
                <Avatar student={child} size="sm" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-semibold text-ink">{child.full_name}</span>
                  <span className="block truncate text-xs text-ink-secondary">{child.group?.name ?? '—'}</span>
                </span>
                {child.id === student.id ? <Check className="size-4 text-brand-600" aria-hidden /> : null}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

function Logo({ subtitle }: { subtitle?: string }) {
  return (
    <div className="flex items-center gap-2.5">
      <img src={logo} alt="" className="size-9 shrink-0 object-contain" />
      <span className="leading-tight">
        <span className="block text-[15px] font-extrabold tracking-tight text-ink">Okurmen<span className="text-brand-600">KIDS</span></span>
        {subtitle ? <span className="block text-[11px] font-medium text-ink-muted">{subtitle}</span> : null}
      </span>
    </div>
  )
}

function SidebarLink({ item }: { item: NavItem }) {
  const { t } = usePortalI18n()
  return (
    <NavLink to={item.to} end={item.end}
      className={({ isActive }) => cn('sp-press group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold',
        isActive ? 'bg-brand-50 text-brand-700' : 'text-ink-secondary hover:bg-surface-hover hover:text-ink')}>
      {({ isActive }) => (
        <>
          <span className={cn('absolute inset-y-2 left-0 w-1 rounded-r-full bg-brand-500 transition-opacity', isActive ? 'opacity-100' : 'opacity-0')} aria-hidden />
          <span className={cn('flex size-8 items-center justify-center rounded-lg transition-colors',
            isActive ? 'bg-brand-500 text-white shadow-sm' : 'bg-surface-muted text-ink-muted group-hover:text-ink')}>
            <item.icon className="size-[17px]" aria-hidden />
          </span>
          {t(item.key)}
        </>
      )}
    </NavLink>
  )
}

function MoreSheet({ items, onClose }: { items: NavItem[]; onClose: () => void }) {
  const { t } = usePortalI18n()
  const { logout } = useAuth()
  return (
    <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label={t('nav.menu')}>
      <button type="button" className="absolute inset-0 bg-ink/30 backdrop-blur-[2px]" aria-label={t('nav.close')} onClick={onClose} />
      <div className="sp-sheet absolute inset-x-0 bottom-0 rounded-t-3xl bg-surface px-4 pb-[calc(env(safe-area-inset-bottom)+1rem)] pt-3 shadow-2xl">
        <div className="mx-auto mb-3 h-1.5 w-10 rounded-full bg-border" aria-hidden />
        <div className="mb-3"><StudentCard /></div>
        <nav className="grid grid-cols-2 gap-2" aria-label={t('nav.menu')}>
          {items.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} onClick={onClose}
              className={({ isActive }) => cn('sp-press flex items-center gap-3 rounded-2xl p-3 text-sm font-semibold ring-1',
                isActive ? 'bg-brand-50 text-brand-700 ring-brand-200' : 'text-ink ring-border/70 hover:bg-surface-hover')}>
              <span className="flex size-9 items-center justify-center rounded-xl bg-surface-muted text-brand-600"><item.icon className="size-[18px]" aria-hidden /></span>
              {t(item.key)}
            </NavLink>
          ))}
        </nav>
        <div className="mt-4 flex items-center justify-between border-t border-border/70 pt-4">
          <LangSwitch />
          <button type="button" onClick={logout} className="sp-press inline-flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold text-ink-secondary hover:bg-surface-hover hover:text-ink">
            <LogOut className="size-4" aria-hidden />{t('nav.logout')}
          </button>
        </div>
      </div>
    </div>
  )
}

function Shell() {
  const { me, student } = usePortal()
  const { t } = usePortalI18n()
  const { logout } = useAuth()
  const location = useLocation()
  const [more, setMore] = useState(false)
  useEffect(() => setMore(false), [location.pathname])
  const items = NAV.filter((item) => !item.payments || me.can_view_payments)
  const bottom = items.filter((item) => BOTTOM.includes(item.to))
  const rest = items.filter((item) => !BOTTOM.includes(item.to))
  const restActive = rest.some((item) => location.pathname.startsWith(item.to))

  return (
    <div className="sp-root min-h-dvh overflow-x-hidden bg-[#f6f8f6]">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[17rem] flex-col border-r border-border/60 bg-surface px-4 pb-4 pt-5 lg:flex">
        <div className="mb-5 px-1"><Logo subtitle={t('brand.portal')} /></div>
        <StudentCard />
        <nav className="mt-5 flex-1 space-y-1 overflow-y-auto" aria-label={t('brand.portal')}>
          {items.map((item) => <SidebarLink key={item.to} item={item} />)}
        </nav>
        <div className="flex items-center justify-between gap-2 border-t border-border/70 pt-4">
          <LangSwitch />
          <button type="button" onClick={logout} className="sp-press inline-flex items-center gap-1.5 rounded-xl px-2.5 py-2 text-sm font-semibold text-ink-secondary hover:bg-surface-hover hover:text-ink">
            <LogOut className="size-4" aria-hidden />{t('nav.logout')}
          </button>
        </div>
      </aside>

      {/* Phone / tablet top bar */}
      <header className="sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-border/60 bg-surface/90 px-4 py-2.5 backdrop-blur-md lg:hidden">
        <Logo />
        <div className="flex items-center gap-2">
          <LangSwitch />
          <StudentCard compact />
        </div>
      </header>

      <main className="px-4 pb-32 pt-5 sm:px-6 sm:pt-7 lg:ml-[17rem] lg:px-10 lg:pb-14 lg:pt-9">
        <div className="mx-auto w-full max-w-6xl">
          <Outlet key={student.id} />
        </div>
      </main>

      {/* Phone / tablet bottom navigation */}
      <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-border/60 bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-md lg:hidden" aria-label={t('brand.portal')}>
        <div className="mx-auto grid max-w-lg grid-cols-5 px-1">
          {bottom.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} aria-label={t(item.key)}
              className={({ isActive }) => cn('sp-press flex flex-col items-center gap-1 py-2 text-[11px] font-semibold', isActive ? 'text-brand-600' : 'text-ink-muted')}>
              {({ isActive }) => (
                <>
                  <span className={cn('flex h-7 w-12 items-center justify-center rounded-full transition-colors', isActive && 'bg-brand-50')}>
                    <item.icon className="size-5" aria-hidden />
                  </span>
                  <span className="max-w-full truncate px-0.5" aria-hidden>{t(SHORT[item.key] ?? item.key)}</span>
                </>
              )}
            </NavLink>
          ))}
          <button type="button" onClick={() => setMore(true)} aria-expanded={more}
            className={cn('sp-press flex flex-col items-center gap-1 py-2 text-[11px] font-semibold', restActive ? 'text-brand-600' : 'text-ink-muted')}>
            <span className={cn('flex h-7 w-12 items-center justify-center rounded-full', restActive && 'bg-brand-50')}><MoreHorizontal className="size-5" aria-hidden /></span>
            {t('nav.more')}
          </button>
        </div>
      </nav>
      {more ? <MoreSheet items={rest} onClose={() => setMore(false)} /> : null}
    </div>
  )
}

function Gate({ children }: { children?: ReactNode }) {
  const { data: me, isPending, isError, refetch } = usePortalMe()
  const { t } = usePortalI18n()
  const { logout } = useAuth()
  if (isPending) return <div className="sp-root mx-auto max-w-5xl p-6"><Loading /></div>
  if (isError || !me) return <div className="sp-root mx-auto max-w-lg p-6"><LoadError onRetry={() => void refetch()} /></div>
  if (me.must_change_password) {
    return (
      <div className="sp-root flex min-h-dvh items-center justify-center bg-[#f6f8f6] px-4 py-10">
        <div className="sp-card sp-rise w-full max-w-md p-6 sm:p-8">
          <div className="mb-6 flex items-center justify-between">
            <Logo />
            <LangSwitch />
          </div>
          <h1 className="text-2xl font-extrabold tracking-tight text-ink">{t('pwd.title')}</h1>
          <p className="mb-6 mt-1.5 text-sm leading-relaxed text-ink-secondary">{t('pwd.subtitle')}</p>
          <ChangePasswordForm onDone={() => void refetch()} />
          <button type="button" onClick={logout} className="mt-4 text-sm font-medium text-ink-secondary hover:text-ink">{t('nav.logout')}</button>
        </div>
      </div>
    )
  }
  if (me.students.length === 0) return <div className="sp-root mx-auto max-w-lg p-6"><LoadError onRetry={() => void refetch()} /></div>
  return <PortalProvider me={me}>{children ?? <Shell />}</PortalProvider>
}

export function StudentPortalLayout() {
  return (
    <PortalI18nProvider>
      <Gate />
    </PortalI18nProvider>
  )
}
