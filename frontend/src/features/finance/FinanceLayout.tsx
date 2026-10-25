import { Suspense, useState } from 'react'
import {
  AlarmClock,
  ArrowLeft,
  BarChart3,
  Banknote,
  CalendarClock,
  History,
  LayoutDashboard,
  LogOut,
  Menu,
  PiggyBank,
  ReceiptText,
  Settings2,
  Tags,
  TriangleAlert,
  Users,
  Wallet,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { NavLink, Outlet } from 'react-router-dom'

import logo from '@/assets/logo.png'
import { financeApi } from '@/api/finance'
import { Drawer } from '@/components/ui/Drawer'
import { LoadingState } from '@/components/ui/LoadingState'
import { useAuth } from '@/hooks/useAuth'
import { ROLE_LABEL } from '@/lib/roles'
import type { FinanceMe, QueueCounts } from '@/types/finance'
import { cn } from '@/utils/cn'

import { PeriodSwitcher } from './period'
import { FINANCE_KEY, useFinanceMe } from './ui'

type Access = 'money' | 'all' | 'settings' | 'audit'

export interface FinanceNavItem {
  to: string
  label: string
  icon: LucideIcon
  end?: boolean
  badge?: keyof QueueCounts
  tone?: 'danger' | 'warning' | 'info'
  access: Access
}

/** Финансы студентов. Денежные разделы — бухгалтер и директор (только
 * просмотр); «Все студенты» — также менеджер; тарифы и настройки — тем,
 * кто может их менять (бухгалтер). Доступ всё равно проверяет backend. */
export const FINANCE_NAV: FinanceNavItem[] = [
  { to: '/finance', label: 'Dashboard', icon: LayoutDashboard, end: true, access: 'money' },
  { to: '/finance/to-pay', label: 'К оплате', icon: Wallet, badge: 'to_pay', tone: 'info', access: 'money' },
  { to: '/finance/soon', label: 'Скоро оплата', icon: AlarmClock, badge: 'soon', tone: 'warning', access: 'money' },
  { to: '/finance/overdue', label: 'Просроченные', icon: TriangleAlert, badge: 'overdue', tone: 'danger', access: 'money' },
  { to: '/finance/students', label: 'Все студенты', icon: Users, access: 'all' },
  { to: '/finance/payments', label: 'Платежи', icon: Banknote, access: 'money' },
  { to: '/finance/prepayments', label: 'Авансы', icon: PiggyBank, access: 'money' },
  { to: '/finance/receipts', label: 'Чеки', icon: ReceiptText, access: 'money' },
  { to: '/finance/analytics', label: 'Аналитика', icon: BarChart3, access: 'money' },
  { to: '/finance/plans', label: 'Тарифы и программы', icon: Tags, access: 'settings' },
  { to: '/finance/audit', label: 'Журнал операций', icon: History, access: 'audit' },
  { to: '/finance/settings', label: 'Настройки', icon: Settings2, access: 'settings' },
]

export function navFor(me: FinanceMe | undefined): FinanceNavItem[] {
  if (!me) return []
  return FINANCE_NAV.filter((item) => {
    if (item.access === 'all') return me.can_view
    if (item.access === 'money') return me.can_view_money
    if (item.access === 'audit') return me.can_view_audit
    return me.can_manage_settings
  })
}

const BADGE_TONE = {
  danger: 'bg-danger text-white',
  warning: 'bg-warning text-white',
  info: 'bg-brand-500 text-white',
}

const ROW = 'flex h-9 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors'

function NavRow({ item, count, onNavigate }: { item: FinanceNavItem; count?: number; onNavigate?: () => void }) {
  return (
    <NavLink
      to={item.to}
      end={item.end}
      onClick={onNavigate}
      className={({ isActive }) => cn(ROW, isActive
        ? 'bg-brand-50 text-brand-700 shadow-[inset_3px_0_0] shadow-brand-500'
        : 'text-ink-secondary hover:bg-surface-hover hover:text-ink')}
    >
      <item.icon className="size-[18px] shrink-0" aria-hidden />
      <span className="flex-1 truncate">{item.label}</span>
      {count ? (
        <span className={cn('min-w-6 rounded-full px-1.5 py-0.5 text-center text-xs font-semibold tabular-nums',
          BADGE_TONE[item.tone ?? 'info'])} aria-label={`${count} студентов`}>
          {count > 99 ? '99+' : count}
        </span>
      ) : null}
    </NavLink>
  )
}

function NavList({ onNavigate }: { onNavigate?: () => void }) {
  const { user, logout } = useAuth()
  const me = useFinanceMe()
  const counts = useQuery({
    queryKey: [...FINANCE_KEY, 'counts'], queryFn: financeApi.counts, enabled: me.data?.can_view_money ?? false,
    refetchInterval: 2 * 60 * 1000,
  })
  const items = navFor(me.data)
  const back = user?.role === 'assistant' ? '/assistant' : user?.role === 'admin' ? '/app/dashboard' : '/accounting'
  const backLabel = user?.role === 'assistant' ? 'В рабочее место' : user?.role === 'admin' ? 'Вернуться в LMS' : 'Бухгалтерия'
  return (
    <div className="flex h-full flex-col">
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-3" aria-label="Финансы студентов">
        {items.map((item) => (
          <NavRow key={item.to} item={item} count={item.badge ? counts.data?.[item.badge] : undefined} onNavigate={onNavigate} />
        ))}
      </nav>
      <div className="space-y-0.5 border-t border-border px-3 py-3">
        <NavRow item={{ to: back, label: backLabel, icon: user?.role === 'assistant' ? ArrowLeft : CalendarClock, access: 'all' }}
          onNavigate={onNavigate} />
        <button type="button" onClick={logout} className={cn(ROW, 'w-full text-ink-secondary hover:bg-surface-hover hover:text-danger')}>
          <LogOut className="size-[18px] shrink-0" aria-hidden />
          Выйти
        </button>
      </div>
    </div>
  )
}

export function FinanceLayout() {
  const { user } = useAuth()
  const me = useFinanceMe()
  const [menuOpen, setMenuOpen] = useState(false)
  const initials = user ? `${user.first_name.charAt(0)}${user.last_name.charAt(0)}`.toUpperCase() : ''

  return (
    <div className="flex min-h-dvh bg-surface-muted">
      <aside className="sticky top-0 hidden h-dvh w-sidebar shrink-0 flex-col border-r border-border bg-surface lg:flex">
        <div className="flex h-header shrink-0 items-center gap-2.5 border-b border-border px-6">
          <img src={logo} alt="Okurmen Kids" className="size-8 shrink-0 object-contain" />
          <div className="leading-tight">
            <p className="font-semibold text-ink">Финансы</p>
            <p className="text-xs text-ink-secondary">Оплата обучения</p>
          </div>
        </div>
        <div className="min-h-0 flex-1">
          <NavList />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-header shrink-0 items-center justify-between gap-3 border-b border-border bg-surface px-4 sm:px-6 lg:px-8 print:hidden">
          <div className="flex min-w-0 items-center gap-2">
            <img src={logo} alt="" className="size-7 object-contain lg:hidden" />
            <span className="truncate font-semibold text-ink lg:hidden">Финансы</span>
            {me.data?.read_only ? (
              <span className="hidden rounded-full bg-info-soft px-2.5 py-1 text-xs font-medium text-info lg:inline">
                Только просмотр
              </span>
            ) : null}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button type="button" onClick={() => setMenuOpen(true)}
              className="flex h-9 items-center gap-1.5 rounded-lg px-2.5 text-sm font-medium text-ink-secondary hover:bg-surface-hover lg:hidden">
              <Menu className="size-5" aria-hidden />
              <span className="hidden sm:inline">Меню</span>
            </button>
            <div className="hidden items-center gap-2 sm:flex">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-brand-100 text-sm font-semibold text-brand-700">
                {initials}
              </span>
              <div className="max-w-48 leading-tight">
                <p className="truncate text-sm font-medium text-ink">{user?.first_name} {user?.last_name}</p>
                <p className="text-xs text-ink-secondary">{user ? ROLE_LABEL[user.role] : ''}</p>
              </div>
            </div>
          </div>
        </header>

        <main className="flex-1 pb-8">
          <div className="mx-auto w-full max-w-page px-4 pt-6 sm:px-6 lg:px-8">
            {me.data?.can_view_money ? (
              <div className="mb-4 flex flex-wrap items-center justify-end gap-2 print:hidden">
                <span className="text-sm text-ink-secondary">Финансовый период:</span>
                <PeriodSwitcher />
              </div>
            ) : null}
            <Suspense fallback={<LoadingState label="Загрузка страницы…" />}>
              <Outlet />
            </Suspense>
          </div>
        </main>
      </div>

      <Drawer isOpen={menuOpen} onClose={() => setMenuOpen(false)} title="Финансы" side="left">
        <div className="-m-4 h-[calc(100%+2rem)] sm:-m-5 sm:h-[calc(100%+2.5rem)]">
          <NavList onNavigate={() => setMenuOpen(false)} />
        </div>
      </Drawer>
    </div>
  )
}
