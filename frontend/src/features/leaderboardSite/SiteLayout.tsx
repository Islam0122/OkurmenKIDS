import { useEffect } from 'react'
import { GraduationCap, Users } from 'lucide-react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'

import logo from '@/assets/logo.png'
import { cn } from '@/utils/cn'

import { periodQuery } from './usePeriodParams'

const TABS = [
  { to: '/leaderboard', end: true, label: 'Топ студентов', short: 'Студенты', icon: GraduationCap },
  { to: '/leaderboard/groups', end: false, label: 'Топ групп', short: 'Группы', icon: Users },
]

/** «OkurmenKIDS Leaderboard» — the public leaderboard site: no login, no
 * LMS navigation; it reads only the public leaderboard API. */
export function SiteLayout() {
  const { search } = useLocation()
  const query = periodQuery(search)

  useEffect(() => {
    const previous = document.title
    document.title = 'OkurmenKIDS Leaderboard — рейтинг студентов и групп'
    return () => {
      document.title = previous
    }
  }, [])

  return (
    <div className="min-h-dvh overflow-x-clip bg-lb-bg text-ink">
      <header className="sticky top-0 z-40 border-b border-lb-line bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-2.5 sm:gap-6">
          <a href="/leaderboard" className="flex shrink-0 items-center gap-2.5 rounded-lg focus-visible:outline-lb-purple">
            <img src={logo} alt="OkurmenKIDS" className="size-10 rounded-full object-contain" />
            <span className="hidden leading-tight sm:block">
              <span className="block text-sm font-extrabold tracking-tight text-lb-deep">OkurmenKIDS</span>
              <span className="block text-xs font-semibold text-lb-gold">Leaderboard</span>
            </span>
          </a>
          <nav aria-label="Разделы рейтинга" className="ml-auto flex items-center gap-1 rounded-xl bg-lb-bg p-1 sm:ml-0">
            {TABS.map(({ to, end, label, short, icon: Icon }) => (
              <NavLink
                key={to}
                to={`${to}${query}`}
                end={end}
                className={({ isActive }) =>
                  cn(
                    'inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-sm font-semibold transition-colors focus-visible:outline-lb-purple',
                    isActive ? 'bg-white text-lb-purple shadow-sm' : 'text-ink-secondary hover:text-lb-purple',
                  )
                }
              >
                <Icon className="size-4" aria-hidden />
                <span className="sm:hidden">{short}</span>
                <span className="hidden sm:inline">{label}</span>
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 pb-10 pt-5 sm:pt-8">
        <Outlet />
      </main>
      <footer className="mx-auto max-w-7xl px-4 pb-8 text-xs text-ink-muted">
        Рейтинг академии OkurmenKIDS. Баллы рассчитываются автоматически по посещаемости, домашним заданиям и тестам;
        изменения в журнале появляются здесь в течение нескольких минут.
      </footer>
    </div>
  )
}
