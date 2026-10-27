import { Suspense } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'

import logo from '@/assets/logo.png'
import { LoadingState } from '@/components/ui/LoadingState'
import { cn } from '@/utils/cn'

import { COMPANY } from './content'

const NAV = [
  { to: '/careers', label: 'Вакансии', end: true },
  { to: '/careers#about', label: 'О компании', end: false },
  { to: '/careers#benefits', label: 'Почему мы', end: false },
]

/** Карьерный сайт OkurmenKIDS — публичный, без входа и без навигации LMS;
 * читает только публичный API вакансий. */
export function CareersLayout() {
  return (
    <div className="flex min-h-dvh flex-col bg-surface-muted">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-2 focus:z-50 focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2">
        К содержимому
      </a>
      <header className="sticky top-0 z-40 border-b border-border bg-surface/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
          <Link to="/careers" className="flex min-w-0 items-center gap-2.5">
            <img src={logo} alt="" className="size-9 shrink-0 object-contain" />
            <span className="truncate text-base font-semibold text-ink">
              {COMPANY.name} <span className="text-brand-700">Карьера</span>
            </span>
          </Link>
          <nav aria-label="Разделы сайта" className="hidden items-center gap-1 sm:flex">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) => cn('rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                  isActive && item.end ? 'text-brand-700' : 'text-ink-secondary hover:bg-surface-hover hover:text-ink')}
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main id="main" className="flex-1">
        <Suspense fallback={<LoadingState label="Загрузка…" />}>
          <Outlet />
        </Suspense>
      </main>
      <footer className="border-t border-border bg-surface">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-6 text-sm text-ink-secondary sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p>© {new Date().getFullYear()} {COMPANY.name}. {COMPANY.tagline}.</p>
          <Link to="/careers/privacy" className="text-brand-700 hover:underline">Обработка персональных данных</Link>
        </div>
      </footer>
    </div>
  )
}
