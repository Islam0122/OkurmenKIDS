import { Suspense, useState, type ReactNode } from 'react'
import {
  AlertTriangle,
  BarChart3,
  Briefcase,
  CalendarCheck,
  ClipboardList,
  FileSpreadsheet,
  GraduationCap,
  Headset,
  LayoutDashboard,
  ListTodo,
  LogOut,
  Megaphone,
  Menu,
  ScanLine,
  Settings2,
  TrendingUp,
  UserCog,
  Users,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'

import logo from '@/assets/logo.png'
import { Drawer } from '@/components/ui/Drawer'
import { LoadingState } from '@/components/ui/LoadingState'
import { useAuth } from '@/hooks/useAuth'
import { ROLE_LABEL } from '@/lib/roles'
import { cn } from '@/utils/cn'

import { NotificationsBell } from '../tasks/NotificationsBell'

export interface ShellNavItem {
  to: string
  label: string
  icon: LucideIcon
  end?: boolean
}

/** 14 разделов кабинета операционного директора (ТЗ, часть 4). */
export const OPERATIONS_NAV: ShellNavItem[] = [
  { to: '/operations', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/operations/team-leads', label: 'Тимлиды и ассистенты', icon: Users },
  { to: '/operations/trainers', label: 'Тренеры', icon: GraduationCap },
  { to: '/operations/sales', label: 'Менеджеры продаж', icon: Headset },
  { to: '/operations/sales-head', label: 'РОП', icon: TrendingUp },
  { to: '/operations/marketing', label: 'Маркетинг', icon: Megaphone },
  { to: '/operations/hr', label: 'HR и сотрудники', icon: Briefcase },
  { to: '/operations/attendance', label: 'Посещаемость сотрудников', icon: ScanLine },
  { to: '/operations/tasks', label: 'Задачи', icon: ListTodo },
  { to: '/operations/daily', label: 'Ежедневный контроль', icon: CalendarCheck },
  { to: '/operations/kpi', label: 'KPI и аналитика', icon: BarChart3 },
  { to: '/operations/reports', label: 'Отчёты', icon: FileSpreadsheet },
  { to: '/operations/issues', label: 'Проблемы', icon: AlertTriangle },
  { to: '/operations/settings', label: 'Настройки', icon: Settings2 },
]

const ROW = 'flex h-9 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors'

function NavRow({ item, onNavigate }: { item: ShellNavItem; onNavigate?: () => void }) {
  return (
    <NavLink
      to={item.to}
      end={item.end}
      onClick={onNavigate}
      className={({ isActive }) => cn(ROW, isActive ? 'bg-brand-50 text-brand-700' : 'text-ink-secondary hover:bg-surface-hover hover:text-ink')}
    >
      <item.icon className="size-[18px] shrink-0" aria-hidden />
      <span className="truncate">{item.label}</span>
    </NavLink>
  )
}

function NavList({ items, footer, onNavigate, label }: { items: ShellNavItem[]; footer: ShellNavItem[]; onNavigate?: () => void; label: string }) {
  const { logout } = useAuth()
  return (
    <div className="flex h-full flex-col">
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-3" aria-label={label}>
        {items.map((item) => <NavRow key={item.to} item={item} onNavigate={onNavigate} />)}
      </nav>
      <div className="space-y-0.5 border-t border-border px-3 py-3">
        {footer.map((item) => <NavRow key={item.to} item={item} onNavigate={onNavigate} />)}
        <button type="button" onClick={logout} className={cn(ROW, 'w-full text-ink-secondary hover:bg-surface-hover hover:text-danger')}>
          <LogOut className="size-[18px] shrink-0" aria-hidden />
          Выйти
        </button>
      </div>
    </div>
  )
}

/** Общая оболочка кабинета (та же, что у HR и маркетинга): меню слева на
 * ноутбуке, выезжающее меню на телефоне, уведомления в шапке. */
export function WorkShell({ title, items, footer, label, children }: { title: string; items: ShellNavItem[]; footer: ShellNavItem[]; label: string; children?: ReactNode }) {
  const { user } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  const initials = user ? `${user.first_name.charAt(0)}${user.last_name.charAt(0)}`.toUpperCase() : ''

  return (
    <div className="flex min-h-dvh bg-surface-muted print:bg-white">
      <aside className="sticky top-0 hidden h-dvh w-sidebar shrink-0 flex-col border-r border-border bg-surface lg:flex print:hidden">
        <div className="flex h-header shrink-0 items-center gap-2.5 border-b border-border px-6">
          <img src={logo} alt="OkurmenKIDS" className="size-8 shrink-0 object-contain" />
          <span className="truncate font-semibold text-ink">{title}</span>
        </div>
        <div className="min-h-0 flex-1">
          <NavList items={items} footer={footer} label={label} />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-header shrink-0 items-center justify-between gap-3 border-b border-border bg-surface px-4 sm:px-6 lg:px-8 print:hidden">
          <div className="flex min-w-0 items-center gap-2">
            <img src={logo} alt="" className="size-7 shrink-0 object-contain lg:hidden" />
            <span className="truncate font-semibold text-ink lg:hidden">{title}</span>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <NotificationsBell />
            <button type="button" onClick={() => setMenuOpen(true)} className="flex h-9 items-center gap-1.5 rounded-lg px-2.5 text-sm font-medium text-ink-secondary hover:bg-surface-hover lg:hidden">
              <Menu className="size-5" aria-hidden />
              <span className="hidden sm:inline">Меню</span>
            </button>
            <div className="hidden items-center gap-2 sm:flex">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-brand-100 text-sm font-semibold text-brand-700">{initials}</span>
              <div className="max-w-48 leading-tight">
                <p className="truncate text-sm font-medium text-ink">{user?.first_name} {user?.last_name}</p>
                <p className="text-xs text-ink-secondary">{user ? ROLE_LABEL[user.role] : ''}</p>
              </div>
            </div>
          </div>
        </header>

        <main className="flex-1 pb-8">
          <div className="mx-auto w-full max-w-page px-4 pt-6 sm:px-6 lg:px-8">
            <Suspense fallback={<LoadingState label="Загрузка страницы…" />}>{children ?? <Outlet />}</Suspense>
          </div>
        </main>
      </div>

      <Drawer isOpen={menuOpen} onClose={() => setMenuOpen(false)} title="Меню" side="left">
        <div className="-m-4 h-[calc(100%+2rem)] sm:-m-5 sm:h-[calc(100%+2.5rem)]">
          <NavList items={items} footer={footer} label={label} onNavigate={() => setMenuOpen(false)} />
        </div>
      </Drawer>
    </div>
  )
}

const FOOTER: ShellNavItem[] = [
  { to: '/tasks', label: 'Мои задачи', icon: ClipboardList },
  { to: '/operations/employees', label: 'Все сотрудники', icon: UserCog },
  { to: '/attendance', label: 'Моя отметка прихода', icon: ScanLine },
]

export function OperationsLayout() {
  return <WorkShell title="Операции" items={OPERATIONS_NAV} footer={FOOTER} label="Разделы кабинета операционного директора" />
}
