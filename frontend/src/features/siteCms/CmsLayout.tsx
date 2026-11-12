import { Suspense, useEffect, useState } from 'react'
import { ArrowLeft, ExternalLink, LogOut, Menu as MenuIcon, X } from 'lucide-react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'

import logo from '@/assets/logo.png'
import { LoadingState } from '@/components/ui/LoadingState'
import { useAuth } from '@/hooks/useAuth'
import { ROLE_LABEL } from '@/lib/roles'
import { cn } from '@/utils/cn'
import { WorkdayButton } from '@/features/marketing/Workday'
import { WorkTools } from '@/features/tasks/WorkTools'

import { useSiteMeta, useSiteOverview } from './api'
import { CMS_MOBILE, CMS_NAV, navFor, type CmsNavGroup, type CmsNavItem } from './nav'
import { useCmsTheme } from './ui'

export const EDITOR_ROLES = ['marketing', 'admin', 'director']

/**
 * «Управление сайтом» — единое рабочее пространство CMS публичного сайта
 * (backend apps.website.cms): навигация по группам «Контент / Медиа /
 * Обратная связь / Настройки», на телефоне — нижняя панель и полное меню.
 */
export function CmsLayout() {
  useCmsTheme()
  const { user, logout } = useAuth()
  const isEditor = Boolean(user && EDITOR_ROLES.includes(user.role))
  const meta = useSiteMeta()
  const site = meta.data?.public_site_url ?? null
  const overview = useSiteOverview(isEditor)
  const counters: Record<string, number> = { leads_new: overview.data?.leads_new ?? 0 }
  const groups = navFor(isEditor)
  const [menu, setMenu] = useState(false)
  const { pathname } = useLocation()
  useEffect(() => setMenu(false), [pathname])

  const initials = user ? `${user.first_name.charAt(0)}${user.last_name.charAt(0)}`.toUpperCase() : ''

  return (
    <div className="flex min-h-dvh bg-surface-muted">
      <a href="#cms-main" className="sr-only z-50 rounded-lg bg-brand-500 px-4 py-2 text-white focus:not-sr-only focus:fixed focus:top-3 focus:left-3">
        Перейти к содержимому
      </a>
      <aside className="sticky top-0 hidden h-dvh w-64 shrink-0 flex-col border-r border-border bg-surface lg:flex">
        <Brand />
        <Nav groups={groups} counters={counters} className="flex-1 overflow-y-auto px-3 py-3" />
        <SidebarFooter isMarketing={user?.role === 'marketing'} onLogout={logout} />
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-header shrink-0 items-center justify-between gap-2 border-b border-border bg-surface/95 px-4 backdrop-blur sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-2">
            <button type="button" onClick={() => setMenu(true)} aria-label="Открыть меню" aria-expanded={menu}
              className="-ml-2 flex size-10 items-center justify-center rounded-lg text-ink-secondary hover:bg-surface-hover lg:hidden">
              <MenuIcon className="size-5" aria-hidden />
            </button>
            <img src={logo} alt="" className="size-7 shrink-0 object-contain lg:hidden" />
            <span className="truncate font-semibold text-ink lg:hidden">Сайт</span>
            {site ? (
              <a href={site} target="_blank" rel="noreferrer" className="hidden items-center gap-2 rounded-full bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700 ring-1 ring-emerald-200 hover:bg-emerald-100 lg:inline-flex">
                <span className="size-1.5 rounded-full bg-emerald-500" aria-hidden />
                {site.replace(/^https?:\/\//, '')}
                <ExternalLink className="size-3" aria-hidden />
              </a>
            ) : null}
          </div>
          <div className="flex shrink-0 items-center gap-2 sm:gap-3">
            {user?.role === 'marketing' ? <><WorkTools /><WorkdayButton /></> : null}
            <div className="hidden items-center gap-2 sm:flex">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-brand-100 text-sm font-semibold text-brand-700" aria-hidden>{initials}</span>
              <div className="max-w-44 leading-tight">
                <p className="truncate text-sm font-medium text-ink">{user?.first_name} {user?.last_name}</p>
                <p className="text-xs text-ink-secondary">{user ? ROLE_LABEL[user.role] : ''}</p>
              </div>
            </div>
          </div>
        </header>

        <main id="cms-main" className="flex-1 pb-[calc(var(--spacing-mobile-nav)+env(safe-area-inset-bottom)+1.5rem)] lg:pb-10">
          <div className="mx-auto w-full max-w-page px-4 pt-5 sm:px-6 sm:pt-7 lg:px-8">
            <Suspense fallback={<LoadingState label="Загрузка страницы…" />}>
              <Outlet />
            </Suspense>
          </div>
        </main>
      </div>

      {/* Phone: the full navigation in a sheet */}
      {menu ? (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Меню сайта"
          onKeyDown={(e) => e.key === 'Escape' && setMenu(false)}>
          <button type="button" aria-label="Закрыть меню" className="absolute inset-0 bg-ink/40" onClick={() => setMenu(false)} />
          <div className="absolute inset-y-0 left-0 flex w-[min(20rem,86vw)] flex-col bg-surface shadow-xl">
            <div className="flex items-center justify-between border-b border-border pr-2">
              <Brand />
              <button type="button" onClick={() => setMenu(false)} aria-label="Закрыть меню" autoFocus
                className="flex size-10 items-center justify-center rounded-lg text-ink-secondary hover:bg-surface-hover">
                <X className="size-5" aria-hidden />
              </button>
            </div>
            <Nav groups={groups} counters={counters} className="flex-1 overflow-y-auto px-3 py-3" large />
            <SidebarFooter isMarketing={user?.role === 'marketing'} onLogout={logout} />
          </div>
        </div>
      ) : null}

      <MobileBar items={isEditor ? CMS_MOBILE : CMS_MOBILE.filter((i) => i.badge)} counters={counters} onMenu={() => setMenu(true)} />
    </div>
  )
}

function Brand() {
  return (
    <div className="flex h-header shrink-0 items-center gap-2.5 px-5">
      <img src={logo} alt="OkurmenKIDS" className="size-8 shrink-0 object-contain" />
      <div className="leading-tight">
        <p className="font-display text-[0.9375rem] font-bold text-ink">Управление сайтом</p>
        <p className="text-xs text-ink-muted">Okurmen Kids Digital</p>
      </div>
    </div>
  )
}

const ROW = 'group flex items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors'

function Nav({ groups, counters, className, large }: { groups: CmsNavGroup[]; counters: Record<string, number>; className?: string; large?: boolean }) {
  return (
    <nav className={className} aria-label="Разделы управления сайтом">
      {groups.map((group) => (
        <div key={group.key} className="mb-3 last:mb-0">
          {group.label ? <p className="px-3 pt-2 pb-1 text-[0.6875rem] font-semibold tracking-[0.08em] text-ink-muted uppercase">{group.label}</p> : null}
          <ul className="space-y-0.5">
            {group.items.map((item) => (
              <li key={item.to}><NavRow item={item} counters={counters} large={large} /></li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  )
}

function NavRow({ item, counters, large }: { item: CmsNavItem; counters: Record<string, number>; large?: boolean }) {
  const count = item.badge ? counters[item.badge] : 0
  return (
    <NavLink to={item.to} end={item.end}
      className={({ isActive }) => cn(ROW, large ? 'h-11' : 'h-9', item.child && 'ml-5',
        isActive ? 'bg-brand-50 text-brand-700' : 'text-ink-secondary hover:bg-surface-hover hover:text-ink')}>
      {({ isActive }) => (
        <>
          <item.icon className={cn('size-[18px] shrink-0', isActive ? 'text-brand-600' : 'text-ink-muted group-hover:text-ink-secondary')} aria-hidden />
          <span className="truncate">{item.label}</span>
          {count ? <span className="ml-auto rounded-full bg-cms-gold px-1.5 py-0.5 text-[0.6875rem] leading-none font-bold text-brand-700" aria-label={`новых: ${count}`}>{count}</span> : null}
        </>
      )}
    </NavLink>
  )
}

function SidebarFooter({ isMarketing, onLogout }: { isMarketing: boolean; onLogout: () => void }) {
  return (
    <div className="space-y-0.5 border-t border-border px-3 py-3">
      {isMarketing ? (
        <Link to="/marketing" className={cn(ROW, 'h-10 text-ink-secondary hover:bg-surface-hover hover:text-ink')}>
          <ArrowLeft className="size-[18px] shrink-0" aria-hidden /> Кабинет маркетинга
        </Link>
      ) : null}
      <button type="button" onClick={onLogout} className={cn(ROW, 'h-10 w-full text-ink-secondary hover:bg-surface-hover hover:text-danger')}>
        <LogOut className="size-[18px] shrink-0" aria-hidden /> Выйти
      </button>
    </div>
  )
}

const CONTENT_PREFIXES = CMS_NAV.find((g) => g.key === 'content')!.items.map((i) => i.to)

function MobileBar({ items, counters, onMenu }: { items: CmsNavItem[]; counters: Record<string, number>; onMenu: () => void }) {
  const { pathname } = useLocation()
  const active = (item: CmsNavItem) => {
    if (item.end) return pathname === item.to
    if (item.to.endsWith('/pages')) return CONTENT_PREFIXES.some((p) => pathname.startsWith(p))
    return pathname.startsWith(item.to)
  }
  return (
    <nav aria-label="Быстрые разделы" className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-surface pb-[env(safe-area-inset-bottom)] lg:hidden">
      <div className="grid h-mobile-nav" style={{ gridTemplateColumns: `repeat(${items.length + 1}, minmax(0, 1fr))` }}>
        {items.map((item) => {
          const on = active(item)
          const count = item.badge ? counters[item.badge] : 0
          return (
            <Link key={item.to} to={item.to} aria-current={on ? 'page' : undefined}
              className={cn('relative flex min-w-0 flex-col items-center justify-center gap-1 text-2xs font-medium', on ? 'text-brand-600' : 'text-ink-muted')}>
              <span className={cn('absolute inset-x-4 top-0 h-0.5 rounded-b-full', on ? 'bg-cms-gold' : 'bg-transparent')} aria-hidden />
              <span className="relative">
                <item.icon className="size-5" aria-hidden />
                {count ? <span className="absolute -top-1.5 -right-2.5 rounded-full bg-cms-gold px-1 text-[0.625rem] leading-4 font-bold text-brand-700">{count}</span> : null}
              </span>
              <span className="max-w-full truncate">{item.label}</span>
            </Link>
          )
        })}
        <button type="button" onClick={onMenu} className="flex min-w-0 flex-col items-center justify-center gap-1 text-2xs font-medium text-ink-muted">
          <MenuIcon className="size-5" aria-hidden />
          Меню
        </button>
      </div>
    </nav>
  )
}
