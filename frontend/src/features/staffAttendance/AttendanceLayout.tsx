import { Suspense } from 'react'
import { ArrowLeft, ClipboardList, LogOut, MapPinned, Settings2, UserRound, Users } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Link, NavLink, Outlet } from 'react-router-dom'

import logo from '@/assets/logo.png'
import { LoadingState } from '@/components/ui/LoadingState'
import { useAuth } from '@/hooks/useAuth'
import { useAttendanceMeta } from '@/hooks/useStaffAttendance'
import { ROLE_LABEL } from '@/lib/roles'
import { cn } from '@/utils/cn'

import { personalPathFor, workspaceFor } from './roles'

interface Tab {
  to: string
  label: string
  icon: LucideIcon
  end?: boolean
}

/** Оболочка раздела «Учёт посещаемости»: личный кабинет отметки и (по
 * правам с сервера) отчёты, офисы с QR-кодами и настройки. */
export function AttendanceLayout() {
  const { user, logout } = useAuth()
  // Бухгалтеру админ-API закрыт изоляцией бухгалтерии — не спрашиваем.
  const meta = useAttendanceMeta(user?.role !== 'accountant')
  const access = meta.data?.access
  const workspace = workspaceFor(user?.role)

  const tabs: Tab[] = [{ to: personalPathFor(user?.role), label: 'Мой кабинет', icon: UserRound }]
  // Раздел «Сотрудники» HR-менеджера (права проверяет backend: apps.users.hr).
  if (user?.role === 'hr_manager') tabs.push({ to: '/hr/employees', label: 'Сотрудники', icon: Users })
  if (access?.can_view_reports) tabs.push({ to: '/admin/attendance', label: 'Учёт сотрудников', icon: ClipboardList, end: true })
  if (access?.can_manage) {
    tabs.push({ to: '/admin/attendance/locations', label: 'Офисы и QR', icon: MapPinned })
    tabs.push({ to: '/admin/attendance/settings', label: 'Настройки', icon: Settings2 })
  }

  return (
    <div className="min-h-dvh bg-surface-muted">
      <header className="sticky top-0 z-30 border-b border-border bg-surface">
        <div className="mx-auto flex h-header max-w-7xl items-center justify-between gap-3 px-4 sm:px-6">
          <Link to={personalPathFor(user?.role)} className="flex min-w-0 items-center gap-2.5">
            <img src={logo} alt="OkurmenKIDS" className="size-8 shrink-0 object-contain" />
            <span className="truncate font-semibold text-ink">Учёт посещаемости</span>
          </Link>
          <div className="flex shrink-0 items-center gap-1">
            <div className="mr-2 hidden text-right leading-tight sm:block">
              <p className="max-w-48 truncate text-sm font-medium text-ink">{user?.first_name} {user?.last_name}</p>
              <p className="text-xs text-ink-secondary">{user ? ROLE_LABEL[user.role] : ''}</p>
            </div>
            {workspace ? (
              <Link
                to={workspace.to}
                className="flex h-9 items-center gap-1.5 rounded-lg px-2.5 text-sm font-medium text-ink-secondary hover:bg-surface-hover"
              >
                <ArrowLeft className="size-4" aria-hidden />
                <span className="hidden sm:inline">{workspace.label}</span>
              </Link>
            ) : null}
            <button
              type="button"
              onClick={logout}
              aria-label="Выйти"
              className="flex size-9 items-center justify-center rounded-lg text-ink-secondary hover:bg-surface-hover hover:text-danger"
            >
              <LogOut className="size-4" aria-hidden />
            </button>
          </div>
        </div>
        {tabs.length > 1 ? (
          <nav className="mx-auto flex max-w-7xl gap-1 overflow-x-auto px-4 sm:px-6" aria-label="Разделы учёта посещаемости">
            {tabs.map((tab) => (
              <NavLink
                key={tab.to}
                to={tab.to}
                end={tab.end}
                className={({ isActive }) =>
                  cn(
                    'flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2.5 text-sm font-medium',
                    isActive ? 'border-brand-500 text-brand-700' : 'border-transparent text-ink-secondary hover:text-ink',
                  )
                }
              >
                <tab.icon className="size-4" aria-hidden />
                {tab.label}
              </NavLink>
            ))}
          </nav>
        ) : null}
      </header>
      <main className="mx-auto max-w-7xl px-4 py-5 sm:px-6 sm:py-6">
        <Suspense fallback={<LoadingState />}>
          <Outlet />
        </Suspense>
      </main>
    </div>
  )
}
