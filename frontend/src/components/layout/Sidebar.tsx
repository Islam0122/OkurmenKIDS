import { LogOut } from 'lucide-react'
import { NavLink } from 'react-router-dom'

import { useAuth } from '@/hooks/useAuth'
import { cn } from '@/utils/cn'

import { getNavItems, PROFILE_NAV_ITEM } from './navItems'

export function Sidebar() {
  const { user, logout } = useAuth()
  const navItems = getNavItems(user?.role)

  return (
    <aside className="hidden w-64 shrink-0 flex-col border-r border-border bg-surface lg:flex">
      <div className="flex h-16 items-center gap-2 border-b border-border px-6">
        <span className="flex size-8 items-center justify-center rounded-lg bg-brand-500 text-sm font-bold text-white">
          OK
        </span>
        <span className="font-semibold text-ink">OkurmenKIDS</span>
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4" aria-label="Основная навигация">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                isActive ? 'bg-brand-50 text-brand-700' : 'text-ink-secondary hover:bg-surface-hover hover:text-ink',
              )
            }
          >
            <item.icon className="size-5 shrink-0" aria-hidden />
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="space-y-1 border-t border-border px-3 py-4">
        <NavLink
          to={PROFILE_NAV_ITEM.to}
          className={({ isActive }) =>
            cn(
              'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
              isActive ? 'bg-brand-50 text-brand-700' : 'text-ink-secondary hover:bg-surface-hover hover:text-ink',
            )
          }
        >
          <PROFILE_NAV_ITEM.icon className="size-5 shrink-0" aria-hidden />
          {PROFILE_NAV_ITEM.label}
        </NavLink>
        <button
          type="button"
          onClick={logout}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-ink-secondary transition-colors hover:bg-surface-hover hover:text-danger"
        >
          <LogOut className="size-5 shrink-0" aria-hidden />
          Выйти
        </button>
      </div>
    </aside>
  )
}
