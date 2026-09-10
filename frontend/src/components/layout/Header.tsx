import { useState } from 'react'
import { LogOut, Menu } from 'lucide-react'
import { NavLink } from 'react-router-dom'

import { Drawer } from '@/components/ui/Drawer'
import { useAuth } from '@/hooks/useAuth'
import { cn } from '@/utils/cn'

import { MOBILE_MORE_NAV } from './navItems'

export function Header() {
  const { user, logout } = useAuth()
  const [isMoreOpen, setIsMoreOpen] = useState(false)

  const initials = user ? `${user.first_name.charAt(0)}${user.last_name.charAt(0)}`.toUpperCase() : ''

  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-border bg-surface px-4 lg:px-6">
      <div className="flex items-center gap-2 lg:hidden">
        <span className="flex size-8 items-center justify-center rounded-lg bg-brand-500 text-sm font-bold text-white">
          OK
        </span>
        <span className="font-semibold text-ink">OkurmenKIDS</span>
      </div>

      <div className="hidden lg:block" />

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => setIsMoreOpen(true)}
          className="flex items-center gap-1.5 rounded-lg px-2.5 py-2 text-sm font-medium text-ink-secondary hover:bg-surface-hover lg:hidden"
        >
          <Menu className="size-5" aria-hidden />
          Ещё
        </button>

        <div className="hidden items-center gap-2 sm:flex">
          <span className="flex size-9 items-center justify-center rounded-full bg-brand-100 text-sm font-semibold text-brand-700">
            {initials}
          </span>
          <div className="leading-tight">
            <p className="text-sm font-medium text-ink">
              {user?.first_name} {user?.last_name}
            </p>
            <p className="text-xs text-ink-secondary">Тренер</p>
          </div>
        </div>

        <button
          type="button"
          onClick={logout}
          aria-label="Выйти из аккаунта"
          className="hidden size-9 items-center justify-center rounded-full text-ink-muted hover:bg-surface-hover hover:text-danger lg:flex"
        >
          <LogOut className="size-5" aria-hidden />
        </button>
      </div>

      <Drawer isOpen={isMoreOpen} onClose={() => setIsMoreOpen(false)} title="Другие разделы" side="bottom">
        <nav className="grid grid-cols-2 gap-2">
          {MOBILE_MORE_NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={() => setIsMoreOpen(false)}
              className={({ isActive }) =>
                cn(
                  'flex flex-col items-center gap-2 rounded-xl border border-border px-4 py-4 text-sm font-medium',
                  isActive ? 'border-brand-200 bg-brand-50 text-brand-700' : 'text-ink-secondary hover:bg-surface-hover',
                )
              }
            >
              <item.icon className="size-5" aria-hidden />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <button
          type="button"
          onClick={logout}
          className="mt-4 flex w-full items-center justify-center gap-2 rounded-lg border border-border px-3 py-2.5 text-sm font-medium text-danger hover:bg-danger-soft"
        >
          <LogOut className="size-4" aria-hidden />
          Выйти
        </button>
      </Drawer>
    </header>
  )
}
