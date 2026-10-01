import { NavLink } from 'react-router-dom'

import { useAuth } from '@/hooks/useAuth'
import { cn } from '@/utils/cn'

import { getMobilePrimaryNav } from './navItems'

/** Phone bottom bar: fixed 64px height (+ the safe-area inset), five equal
 * columns, one-line labels — so it never changes height or width between
 * pages, and AppLayout reserves exactly its height below the content. */
export function MobileNavigation() {
  const { user } = useAuth()
  const items = getMobilePrimaryNav(user?.role)

  return (
    <nav
      aria-label="Основная навигация"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-surface pb-[env(safe-area-inset-bottom)] lg:hidden"
    >
      <div className="grid h-mobile-nav" style={{ gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))` }}>
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              cn(
                'relative flex min-w-0 flex-col items-center justify-center gap-1 text-2xs font-medium transition-colors',
                isActive ? 'text-brand-600' : 'text-ink-muted hover:text-ink',
              )
            }
          >
            {({ isActive }) => (
              <>
                <span
                  className={cn('absolute inset-x-3 top-0 h-0.5 rounded-b-full', isActive ? 'bg-brand-500' : 'bg-transparent')}
                  aria-hidden
                />
                <item.icon className="size-5 shrink-0" aria-hidden />
                <span className="max-w-full truncate">{item.shortLabel ?? item.label}</span>
              </>
            )}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
