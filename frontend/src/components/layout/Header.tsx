import { useState } from 'react'
import { LogOut, Menu } from 'lucide-react'
import { NavLink } from 'react-router-dom'

import logo from '@/assets/logo.png'
import { Drawer } from '@/components/ui/Drawer'
import { useAuth } from '@/hooks/useAuth'
import { isTeamLead, ROLE_LABEL } from '@/lib/roles'
import { cn } from '@/utils/cn'

import { getMobileMoreNav } from './navItems'
import { NewsBell } from './NewsBell'
import { TeamLeadNav } from './TeamLeadNav'

export function Header() {
  const { user, logout } = useAuth()
  const [isMoreOpen, setIsMoreOpen] = useState(false)
  const moreNavItems = getMobileMoreNav(user?.role)
  const teamLead = isTeamLead(user?.role)

  const initials = user ? `${user.first_name.charAt(0)}${user.last_name.charAt(0)}`.toUpperCase() : ''

  return (
    <header className="sticky top-0 z-30 flex h-header shrink-0 items-center justify-between gap-3 border-b border-border bg-surface px-4 sm:px-6 lg:px-8">
      <div className="flex min-w-0 items-center gap-2 lg:hidden">
        <img src={logo} alt="OkurmenKIDS" className="size-8 shrink-0 object-contain" />
        <span className="hidden truncate font-semibold text-ink min-[360px]:inline">OkurmenKIDS</span>
      </div>

      <div className="hidden lg:block" />

      <div className="flex shrink-0 items-center gap-2">
        <button
          type="button"
          onClick={() => setIsMoreOpen(true)}
          className="flex h-9 items-center gap-1.5 rounded-lg px-2.5 text-sm font-medium text-ink-secondary hover:bg-surface-hover lg:hidden"
        >
          <Menu className="size-5" aria-hidden />
          {teamLead ? 'Меню' : 'Ещё'}
        </button>

        {/* News is the Trainer feed (backend: IsTeacher) — not a Team Lead's. */}
        {isTeamLead(user?.role) ? null : <NewsBell />}

        <div className="hidden items-center gap-2 sm:flex">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-brand-100 text-sm font-semibold text-brand-700">
            {initials}
          </span>
          <div className="max-w-48 leading-tight">
            <p className="truncate text-sm font-medium text-ink">
              {user?.first_name} {user?.last_name}
            </p>
            <p className="text-xs text-ink-secondary">{user ? ROLE_LABEL[user.role] : ''}</p>
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

      {/* Team Lead: the same sectioned sidebar, as a drawer on tablet / phone. */}
      <Drawer isOpen={teamLead && isMoreOpen} onClose={() => setIsMoreOpen(false)} title="Меню" side="left">
        <div className="-m-4 flex h-[calc(100%+2rem)] flex-col sm:-m-5 sm:h-[calc(100%+2.5rem)]">
          <div className="min-h-0 flex-1">
            <TeamLeadNav onNavigate={() => setIsMoreOpen(false)} />
          </div>
          <div className="border-t border-border px-3 py-3">
            <button type="button" onClick={logout}
              className="flex h-9 w-full items-center gap-3 rounded-lg px-3 text-sm font-medium text-ink-secondary hover:bg-surface-hover hover:text-danger">
              <LogOut className="size-[18px] shrink-0" aria-hidden />
              Выйти
            </button>
          </div>
        </div>
      </Drawer>

      <Drawer isOpen={!teamLead && isMoreOpen} onClose={() => setIsMoreOpen(false)} title="Другие разделы" side="bottom">
        <nav className="grid grid-cols-2 gap-2">
          {moreNavItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={() => setIsMoreOpen(false)}
              className={({ isActive }) =>
                cn(
                  'flex min-w-0 flex-col items-center gap-2 rounded-xl border border-border p-4 text-center text-sm font-medium',
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
          className="mt-4 flex h-10 w-full items-center justify-center gap-2 rounded-lg border border-border px-4 text-sm font-medium text-danger hover:bg-danger-soft"
        >
          <LogOut className="size-4" aria-hidden />
          Выйти
        </button>
      </Drawer>
    </header>
  )
}
