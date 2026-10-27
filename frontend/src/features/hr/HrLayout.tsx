import { Suspense, useState } from 'react'
import { BarChart3, Briefcase, CalendarDays, LayoutDashboard, LogOut, Menu, ScanLine, UserSearch, Users } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'

import logo from '@/assets/logo.png'
import { Drawer } from '@/components/ui/Drawer'
import { LoadingState } from '@/components/ui/LoadingState'
import { useAuth } from '@/hooks/useAuth'
import { ROLE_LABEL } from '@/lib/roles'
import { cn } from '@/utils/cn'

interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  end?: boolean
}

/** Разделы HR-кабинета. Учёт прихода и ухода сотрудников в обязанности HR не
 * входит — внизу только своя отметка, как у бухгалтерии. */
export const HR_NAV: NavItem[] = [
  { to: '/hr', label: 'Главная', icon: LayoutDashboard, end: true },
  { to: '/hr/employees', label: 'Сотрудники', icon: Users },
  { to: '/hr/candidates', label: 'Кандидаты', icon: UserSearch },
  { to: '/hr/interviews', label: 'Собеседования', icon: CalendarDays },
  { to: '/hr/vacancies', label: 'Вакансии', icon: Briefcase },
  { to: '/hr/reports', label: 'Отчёты', icon: BarChart3 },
]

const ROW = 'flex h-9 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors'

function NavRow({ item, onNavigate }: { item: NavItem; onNavigate?: () => void }) {
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

function NavList({ onNavigate }: { onNavigate?: () => void }) {
  const { logout } = useAuth()
  return (
    <div className="flex h-full flex-col">
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-3" aria-label="Навигация HR-кабинета">
        {HR_NAV.map((item) => <NavRow key={item.to} item={item} onNavigate={onNavigate} />)}
      </nav>
      <div className="space-y-0.5 border-t border-border px-3 py-3">
        <NavRow item={{ to: '/attendance', label: 'Моя отметка прихода', icon: ScanLine }} onNavigate={onNavigate} />
        <button type="button" onClick={logout} className={cn(ROW, 'w-full text-ink-secondary hover:bg-surface-hover hover:text-danger')}>
          <LogOut className="size-[18px] shrink-0" aria-hidden />
          Выйти
        </button>
      </div>
    </div>
  )
}

/** HR-кабинет — та же оболочка, что у LMS, ассистента и бухгалтерии. */
export function HrLayout() {
  const { user } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  const initials = user ? `${user.first_name.charAt(0)}${user.last_name.charAt(0)}`.toUpperCase() : ''

  return (
    <div className="flex min-h-dvh bg-surface-muted">
      <aside className="sticky top-0 hidden h-dvh w-sidebar shrink-0 flex-col border-r border-border bg-surface lg:flex">
        <div className="flex h-header shrink-0 items-center gap-2.5 border-b border-border px-6">
          <img src={logo} alt="OkurmenKIDS" className="size-8 shrink-0 object-contain" />
          <span className="font-semibold text-ink">HR-кабинет</span>
        </div>
        <div className="min-h-0 flex-1">
          <NavList />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-header shrink-0 items-center justify-between gap-3 border-b border-border bg-surface px-4 sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-2">
            <img src={logo} alt="" className="size-7 shrink-0 object-contain lg:hidden" />
            <span className="truncate font-semibold text-ink lg:hidden">HR-кабинет</span>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={() => setMenuOpen(true)}
              className="flex h-9 items-center gap-1.5 rounded-lg px-2.5 text-sm font-medium text-ink-secondary hover:bg-surface-hover lg:hidden"
            >
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
            <Suspense fallback={<LoadingState label="Загрузка страницы…" />}>
              <Outlet />
            </Suspense>
          </div>
        </main>
      </div>

      <Drawer isOpen={menuOpen} onClose={() => setMenuOpen(false)} title="Меню" side="left">
        <div className="-m-4 h-[calc(100%+2rem)] sm:-m-5 sm:h-[calc(100%+2.5rem)]">
          <NavList onNavigate={() => setMenuOpen(false)} />
        </div>
      </Drawer>
    </div>
  )
}
