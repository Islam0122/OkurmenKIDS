import { useEffect, useState } from 'react'
import { format } from 'date-fns'
import { ru } from 'date-fns/locale'
import { Eye, LogOut } from 'lucide-react'
import { Link, Outlet } from 'react-router-dom'

import logo from '@/assets/logo.png'
import { useAuth } from '@/hooks/useAuth'
import { IS_SCHEDULE_SITE } from '@/lib/appMode'

/** «OkurmenKIDS Schedule» — the standalone, read-only schedule site: its own
 * slim header (no LMS navigation), the same login and API as the LMS. */
export function SiteLayout() {
  const { user, logout } = useAuth()
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 30_000)
    return () => window.clearInterval(id)
  }, [])
  useEffect(() => {
    const previous = document.title
    document.title = 'OkurmenKIDS Schedule'
    return () => {
      document.title = previous
    }
  }, [])

  const name = user ? [user.first_name, user.last_name].filter(Boolean).join(' ') || user.username : ''
  return (
    <div className="min-h-dvh bg-surface-muted">
      <header className="sticky top-0 z-40 border-b border-border bg-surface/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1800px] flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2.5">
          <Link to="/schedule" className="flex items-center gap-2.5">
            <img src={logo} alt="" className="size-8 object-contain" />
            <span className="text-base font-semibold text-ink">
              OkurmenKIDS <span className="text-brand-700">Schedule</span>
            </span>
          </Link>
          <span className="inline-flex items-center gap-1 rounded-full bg-info-soft px-2 py-0.5 text-xs font-medium text-info">
            <Eye className="size-3.5" aria-hidden />Только просмотр
          </span>
          <span className="text-sm text-ink-secondary first-letter:uppercase" aria-label="Текущая дата">
            {format(now, 'EEEE, d MMMM yyyy · HH:mm', { locale: ru })}
          </span>
          <div className="ml-auto flex items-center gap-3 text-sm">
            {!IS_SCHEDULE_SITE ? <Link to="/" className="text-brand-700 hover:underline">LMS</Link> : null}
            <span className="hidden text-ink-secondary sm:inline">{name}</span>
            <button type="button" onClick={logout} className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-ink-secondary hover:bg-surface-hover" aria-label="Выйти">
              <LogOut className="size-4" aria-hidden /><span className="hidden sm:inline">Выйти</span>
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-[1800px] px-4 py-4">
        <Outlet />
      </main>
    </div>
  )
}

/** A signed-in user whose role has no access to the academy schedule. */
export function SiteNoAccess() {
  const { logout } = useAuth()
  return (
    <div className="card mx-auto mt-10 max-w-md p-6 text-center">
      <h1 className="text-lg font-semibold text-ink">Нет доступа к расписанию академии</h1>
      <p className="mt-2 text-sm text-ink-secondary">
        Расписание всей академии открыто администрации, руководителю тренеров и ассистентам. Свои занятия тренер видит в LMS.
      </p>
      <div className="mt-4 flex justify-center gap-2">
        <Link to="/app/dashboard" className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600">Открыть LMS</Link>
        <button type="button" onClick={logout} className="rounded-lg border border-border px-4 py-2 text-sm text-ink hover:bg-surface-hover">Выйти</button>
      </div>
    </div>
  )
}
