import { useState } from 'react'
import { LogOut, PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { NavLink } from 'react-router-dom'

import logo from '@/assets/logo.png'
import { useAuth } from '@/hooks/useAuth'
import { cn } from '@/utils/cn'

import { getNavItems, PROFILE_NAV_ITEM } from './navItems'
import type { NavItem } from './navItems'
import { TeamLeadNav } from './TeamLeadNav'

const COLLAPSED_KEY = 'okurmen.sidebar.collapsed'

/** A per-browser convenience: storage may be unavailable (private mode). */
function readCollapsed(): boolean {
  try {
    return window.localStorage.getItem(COLLAPSED_KEY) === '1'
  } catch {
    return false
  }
}

function writeCollapsed(value: boolean) {
  try {
    window.localStorage.setItem(COLLAPSED_KEY, value ? '1' : '0')
  } catch {
    /* not remembered — fine */
  }
}

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
  const { user } = useAuth()
  return user?.role === 'team_lead' ? <TeamLeadSidebar /> : <RoleSidebar />
}

/** Team Lead: sections that open on click; can be collapsed to icons (240px ↔ 72px). */
function TeamLeadSidebar() {
  const { logout } = useAuth()
  const [collapsed, setCollapsed] = useState(readCollapsed)
  const toggle = () => {
    setCollapsed((value) => {
      writeCollapsed(!value)
      return !value
    })
  }
  return (
    <aside
      className={cn(
        'sticky top-0 hidden h-dvh shrink-0 flex-col border-r border-border bg-surface transition-[width] duration-200 lg:flex',
        collapsed ? 'w-[72px]' : 'w-sidebar',
      )}
    >
      <div className={cn('flex h-header shrink-0 items-center gap-2.5 border-b border-border', collapsed ? 'justify-center px-2' : 'px-5')}>
        <img src={logo} alt="OkurmenKIDS" className="size-8 shrink-0 object-contain" />
        {collapsed ? null : <span className="truncate font-semibold text-ink">OkurmenKIDS</span>}
      </div>
      <div className="min-h-0 flex-1">
        <TeamLeadNav collapsed={collapsed} />
      </div>
      <div className={cn('space-y-0.5 border-t border-border py-3', collapsed ? 'px-2' : 'px-3')}>
        <button
          type="button"
          onClick={toggle}
          title={collapsed ? 'Развернуть меню' : undefined}
          aria-label={collapsed ? 'Развернуть меню' : 'Свернуть меню'}
          className={cn('flex h-9 w-full items-center gap-3 rounded-lg px-3 text-sm font-medium text-ink-secondary hover:bg-surface-hover hover:text-ink', collapsed && 'justify-center px-0')}
        >
          {collapsed ? <PanelLeftOpen className="size-[18px] shrink-0" aria-hidden /> : <PanelLeftClose className="size-[18px] shrink-0" aria-hidden />}
          {collapsed ? null : 'Свернуть меню'}
        </button>
        <button
          type="button"
          onClick={logout}
          title={collapsed ? 'Выйти' : undefined}
          aria-label={collapsed ? 'Выйти' : undefined}
          className={cn('flex h-9 w-full items-center gap-3 rounded-lg px-3 text-sm font-medium text-ink-secondary hover:bg-surface-hover hover:text-danger', collapsed && 'justify-center px-0')}
        >
          <LogOut className="size-[18px] shrink-0" aria-hidden />
          {collapsed ? null : 'Выйти'}
        </button>
      </div>
    </aside>
  )
}

function RoleSidebar() {
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
