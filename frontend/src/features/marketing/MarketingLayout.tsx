import { Suspense } from 'react'
import { BarChart3, CalendarRange, ClipboardCheck, LayoutDashboard, LogOut, ScanLine, Target, Wallet } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'

import logo from '@/assets/logo.png'
import { LoadingState } from '@/components/ui/LoadingState'
import { useAuth } from '@/hooks/useAuth'
import { ROLE_LABEL } from '@/lib/roles'
import { cn } from '@/utils/cn'

import { WorkdayButton } from './Workday'
import { WorkTools } from '@/features/tasks/WorkTools'

interface NavItem {
  to: string
  label: string
  /** Подпись в нижней панели телефона: пять пунктов должны уместиться в 320px. */
  shortLabel?: string
  icon: LucideIcon
  end?: boolean
}

/** Разделы кабинета маркетинга. Приход и уход — кнопка в шапке
 * (существующий механизм посещаемости), история — /attendance. «Моя
 * зарплата» — только собственные начисления и выплаты (/accounting/my/). */
export const MARKETING_NAV: NavItem[] = [
  { to: '/marketing', label: 'Обзор', icon: LayoutDashboard, end: true },
  { to: '/marketing/content', label: 'Контент-план', shortLabel: 'План', icon: CalendarRange },
  { to: '/marketing/tasks', label: 'Задачи', icon: ClipboardCheck },
  { to: '/marketing/reports', label: 'Отчёты', icon: BarChart3 },
  { to: '/marketing/my-salary', label: 'Моя зарплата', shortLabel: 'Зарплата', icon: Wallet },
]

/** Только в боковом меню: нижняя панель телефона вмещает пять разделов, на
 * телефоне «Кампании» открываются из «Обзора». */
export const MARKETING_SIDEBAR_EXTRA: NavItem[] = [
  { to: '/marketing/campaigns', label: 'Кампании', icon: Target },
]

const ROW = 'flex h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors'

/** Кабинет маркетинга — та же оболочка, что у HR и LMS: боковое меню на
 * ноутбуке, нижняя панель из пяти разделов на телефоне. */
export function MarketingLayout() {
  const { user, logout } = useAuth()
  const initials = user ? `${user.first_name.charAt(0)}${user.last_name.charAt(0)}`.toUpperCase() : ''

  return (
    <div className="flex min-h-dvh bg-surface-muted">
      <aside className="sticky top-0 hidden h-dvh w-sidebar shrink-0 flex-col border-r border-border bg-surface lg:flex">
        <div className="flex h-header shrink-0 items-center gap-2.5 border-b border-border px-6">
          <img src={logo} alt="OkurmenKIDS" className="size-8 shrink-0 object-contain" />
          <span className="font-semibold text-ink">Маркетинг</span>
        </div>
        <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-3" aria-label="Разделы кабинета маркетинга">
          {[...MARKETING_NAV, ...MARKETING_SIDEBAR_EXTRA].map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => cn(ROW, isActive ? 'bg-brand-50 text-brand-700' : 'text-ink-secondary hover:bg-surface-hover hover:text-ink')}
            >
              <item.icon className="size-[18px] shrink-0" aria-hidden />
              <span className="truncate">{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="space-y-0.5 border-t border-border px-3 py-3">
          <NavLink to="/attendance/staff" className={cn(ROW, 'text-ink-secondary hover:bg-surface-hover hover:text-ink')}>
            <ScanLine className="size-[18px] shrink-0" aria-hidden />
            История посещений
          </NavLink>
          <button type="button" onClick={logout} className={cn(ROW, 'w-full text-ink-secondary hover:bg-surface-hover hover:text-danger')}>
            <LogOut className="size-[18px] shrink-0" aria-hidden />
            Выйти
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-header shrink-0 items-center justify-between gap-2 border-b border-border bg-surface/95 px-4 backdrop-blur sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-2">
            <img src={logo} alt="" className="size-7 shrink-0 object-contain lg:hidden" />
            <span className="truncate font-semibold text-ink lg:hidden">Маркетинг</span>
          </div>
          <div className="flex shrink-0 items-center gap-2 sm:gap-3">
            <WorkTools />
            <WorkdayButton />
            <div className="hidden items-center gap-2 sm:flex">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-brand-100 text-sm font-semibold text-brand-700" aria-hidden>
                {initials}
              </span>
              <div className="max-w-44 leading-tight">
                <p className="truncate text-sm font-medium text-ink">{user?.first_name} {user?.last_name}</p>
                <p className="text-xs text-ink-secondary">{user ? ROLE_LABEL[user.role] : ''}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={logout}
              aria-label="Выйти"
              className="flex size-10 items-center justify-center rounded-lg text-ink-secondary hover:bg-surface-hover hover:text-danger lg:hidden"
            >
              <LogOut className="size-5" aria-hidden />
            </button>
          </div>
        </header>

        <main className="flex-1 pb-[calc(var(--spacing-mobile-nav)+env(safe-area-inset-bottom)+1.5rem)] lg:pb-8">
          <div className="mx-auto w-full max-w-page px-4 pt-5 sm:px-6 sm:pt-6 lg:px-8">
            <Suspense fallback={<LoadingState label="Загрузка страницы…" />}>
              <Outlet />
            </Suspense>
          </div>
        </main>
      </div>

      <nav
        aria-label="Разделы кабинета маркетинга"
        className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-surface pb-[env(safe-area-inset-bottom)] lg:hidden"
      >
        <div className="grid h-mobile-nav grid-cols-5">
          {MARKETING_NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn('relative flex min-w-0 flex-col items-center justify-center gap-1 text-2xs font-medium transition-colors', isActive ? 'text-brand-600' : 'text-ink-muted hover:text-ink')
              }
            >
              {({ isActive }) => (
                <>
                  <span className={cn('absolute inset-x-3 top-0 h-0.5 rounded-b-full', isActive ? 'bg-brand-500' : 'bg-transparent')} aria-hidden />
                  <item.icon className="size-5 shrink-0" aria-hidden />
                  <span className="max-w-full truncate">{item.shortLabel ?? item.label}</span>
                </>
              )}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  )
}
