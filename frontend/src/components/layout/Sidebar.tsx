import { LogOut } from 'lucide-react'
import { NavLink } from 'react-router-dom'

import logo from '@/assets/logo.png'
import { useAuth } from '@/hooks/useAuth'
import { cn } from '@/utils/cn'

import { getNavItems, PROFILE_NAV_ITEM } from './navItems'
import type { NavItem } from './navItems'

const ITEM_CLASSES = 'flex h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors'

function SidebarLink({ item }: { item: NavItem }) {
  return (
    <NavLink
      to={item.to}
      className={({ isActive }) =>
        cn(ITEM_CLASSES, isActive ? 'bg-brand-50 text-brand-700' : 'text-ink-secondary hover:bg-surface-hover hover:text-ink')
      }
    >
      <item.icon className="size-5 shrink-0" aria-hidden />
      <span className="truncate">{item.label}</span>
    </NavLink>
  )
}

/** Desktop navigation: a fixed-width column pinned to the viewport height,
 * so it never grows/shrinks with the page and its nav scrolls on its own. */
export function Sidebar() {
  const { user, logout } = useAuth()
  const navItems = getNavItems(user?.role)

  return (
    <aside className="sticky top-0 hidden h-dvh w-sidebar shrink-0 flex-col border-r border-border bg-surface lg:flex">
      <div className="flex h-header shrink-0 items-center gap-2.5 border-b border-border px-6">
        <img src={logo} alt="OkurmenKIDS" className="size-8 shrink-0 object-contain" />
        <span className="font-semibold text-ink">OkurmenKIDS</span>
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4" aria-label="Основная навигация">
        {navItems.map((item) => (
          <SidebarLink key={item.to} item={item} />
        ))}
      </nav>

      <div className="space-y-1 border-t border-border px-3 py-4">
        <SidebarLink item={PROFILE_NAV_ITEM} />
        <button
          type="button"
          onClick={logout}
          className={cn(ITEM_CLASSES, 'w-full text-ink-secondary hover:bg-surface-hover hover:text-danger')}
        >
          <LogOut className="size-5 shrink-0" aria-hidden />
          Выйти
        </button>
      </div>
    </aside>
  )
}
