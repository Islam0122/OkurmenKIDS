import '@fontsource-variable/manrope'

import { useEffect, useState, type ReactNode } from 'react'
import { LogIn, LogOut } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'

import logo from '@/assets/logo.png'
import { useAuth } from '@/hooks/useAuth'
import { ROLE_LABEL } from '@/lib/roles'
import type { User } from '@/types/auth'

import { PORTAL_PATH } from './config'

/** Dark full-screen frame shared by the launcher and the programs page. */
export function PortalShell({ children }: { children: ReactNode }) {
  useEffect(() => {
    const previous = document.title
    document.title = 'OKURMEN DIGITAL'
    return () => {
      document.title = previous
    }
  }, [])

  return (
    <div className="relative isolate flex min-h-dvh flex-col overflow-x-hidden bg-pd-bg font-display text-pd-ink antialiased selection:bg-pd-green/30">
      <div aria-hidden className="pd-grid pointer-events-none fixed inset-0 -z-10" />
      <div
        aria-hidden
        className="pointer-events-none fixed left-1/2 top-[-18rem] -z-10 h-[30rem] w-[52rem] max-w-[140vw] -translate-x-1/2 rounded-full bg-pd-green/[0.06] blur-3xl"
      />
      <PortalHeader />
      {children}
    </div>
  )
}

function PortalHeader() {
  const { user, status, logout } = useAuth()
  const location = useLocation()

  return (
    <header className="mx-auto flex h-16 w-full max-w-[1100px] shrink-0 items-center justify-between gap-3 px-4 sm:px-6">
      <Link to={PORTAL_PATH} className="group flex min-w-0 items-center gap-3 rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-pd-green">
        <span className="grid size-9 shrink-0 place-items-center rounded-lg border border-pd-line bg-pd-panel transition-colors group-hover:border-pd-line-strong">
          <img src={logo} alt="" className="size-6 object-contain" />
        </span>
        <span className="min-w-0 leading-tight">
          <span className="block truncate text-sm font-extrabold tracking-[0.14em]">
            OKURMEN <span className="text-pd-green">DIGITAL</span>
          </span>
          <span className="block truncate text-[11px] font-medium uppercase tracking-[0.18em] text-pd-faint">Education Ecosystem</span>
        </span>
      </Link>

      <div className="flex shrink-0 items-center gap-3">
        <Clock />
        {status === 'authenticated' && user ? (
          <UserChip user={user} onLogout={logout} />
        ) : status === 'loading' ? (
          <span className="h-9 w-24 animate-pulse rounded-lg border border-pd-line bg-pd-panel" aria-label="Проверяем сессию" />
        ) : (
          <Link
            to="/login"
            state={{ from: { pathname: location.pathname, search: location.search } }}
            className="inline-flex h-9 items-center gap-2 rounded-lg border border-pd-line-strong bg-pd-ink px-3.5 text-sm font-semibold text-pd-bg transition hover:bg-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-pd-green"
          >
            <LogIn className="size-4" aria-hidden />
            Login
          </Link>
        )}
      </div>
    </header>
  )
}

function initials(user: User): string {
  const value = `${user.first_name.charAt(0)}${user.last_name.charAt(0)}`.trim()
  return (value || user.username.charAt(0)).toUpperCase()
}

function UserChip({ user, onLogout }: { user: User; onLogout: () => void }) {
  const name = [user.first_name, user.last_name].filter(Boolean).join(' ') || user.username
  return (
    <div className="flex items-center gap-1 rounded-xl border border-pd-line bg-pd-panel/80 p-1 backdrop-blur">
      <span className="grid size-7 place-items-center rounded-lg bg-pd-green/15 text-xs font-bold text-pd-green" aria-hidden>
        {initials(user)}
      </span>
      <span className="hidden max-w-40 px-1.5 leading-tight sm:block">
        <span className="block truncate text-xs font-semibold">{name}</span>
        <span className="block truncate text-[11px] text-pd-faint">{ROLE_LABEL[user.role]}</span>
      </span>
      <button
        type="button"
        onClick={onLogout}
        className="grid size-7 place-items-center rounded-lg text-pd-faint transition hover:bg-pd-panel-hover hover:text-pd-ink focus-visible:outline-2 focus-visible:outline-pd-green"
        aria-label="Log out"
        title="Log out"
      >
        <LogOut className="size-4" aria-hidden />
      </button>
    </div>
  )
}

/** Small live clock in academy time — the "operating system" touch. */
function Clock() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 30_000)
    return () => window.clearInterval(id)
  }, [])
  const time = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Bishkek' }).format(now)
  return (
    <span className="hidden items-center gap-2 font-mono text-xs text-pd-faint md:inline-flex" aria-label={`Bishkek time ${time}`}>
      <span className="size-1.5 rounded-full bg-pd-green shadow-[0_0_8px] shadow-pd-green" aria-hidden />
      {time}
    </span>
  )
}
