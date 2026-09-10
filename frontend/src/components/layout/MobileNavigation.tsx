import { NavLink } from 'react-router-dom'

import { useAuth } from '@/hooks/useAuth'
import { cn } from '@/utils/cn'

import { getMobilePrimaryNav } from './navItems'

export function MobileNavigation() {
  const { user } = useAuth()
  const items = getMobilePrimaryNav(user?.role)

  return (
    <nav
      aria-label="Основная навигация"
      className="fixed inset-x-0 bottom-0 z-40 flex border-t border-border bg-surface pb-[env(safe-area-inset-bottom)] lg:hidden"
    >
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          className={({ isActive }) =>
            cn(
              'flex flex-1 flex-col items-center gap-1 py-2.5 text-xs font-medium',
              isActive ? 'text-brand-600' : 'text-ink-muted',
            )
          }
        >
          <item.icon className="size-5" aria-hidden />
          {item.label}
        </NavLink>
      ))}
    </nav>
  )
}
