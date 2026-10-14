import { useEffect } from 'react'
import { GraduationCap, Trophy, Users } from 'lucide-react'
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
    <div className="min-h-dvh overflow-x-clip bg-lb-bg text-lb-ink">
      <header className="sticky top-0 z-40 border-b border-lb-line/80 bg-white/85 backdrop-blur-md">
        <div className="mx-auto grid h-16 max-w-7xl grid-cols-[auto_1fr] items-center gap-3 px-4 md:grid-cols-[1fr_auto_1fr]">
          <a href="/leaderboard" className="flex min-w-0 items-center gap-2.5 justify-self-start rounded-xl focus-visible:outline-lb-purple">
            <img src={logo} alt="OkurmenKIDS" className="size-10 shrink-0 rounded-full object-contain shadow-[0_0_0_1px_rgba(41,16,100,0.08)]" />
            <span className="hidden leading-none sm:block">
              <span className="block text-[15px] font-black tracking-wide text-lb-deep">OKURMEN KIDS</span>
              <span className="mt-1 block text-[11px] font-bold uppercase tracking-[0.2em] text-lb-gold">Leaderboard</span>
            </span>
          </a>

          <nav aria-label="Разделы рейтинга" className="flex items-center gap-1 justify-self-end md:justify-self-center">
            {TABS.map(({ to, end, label, short, icon: Icon }) => (
              <NavLink
                key={to}
                to={`${to}${query}`}
                end={end}
                className={({ isActive }) =>
                  cn(
                    'relative inline-flex h-10 items-center gap-1.5 rounded-xl px-3 text-sm font-semibold transition-colors focus-visible:outline-lb-purple sm:px-4',
                    'after:absolute after:inset-x-3 after:-bottom-[13px] after:h-[3px] after:rounded-full after:transition-colors',
                    isActive
                      ? 'bg-lb-purple-50 text-lb-purple after:bg-lb-purple'
                      : 'text-lb-muted after:bg-transparent hover:bg-lb-bg hover:text-lb-purple',
                  )
                }
              >
                <Icon className="size-4" aria-hidden />
                <span className="sm:hidden">{short}</span>
                <span className="hidden sm:inline">{label}</span>
              </NavLink>
            ))}
          </nav>

          <div className="hidden items-center gap-2.5 justify-self-end md:flex">
            <span className="text-right text-xs font-semibold leading-tight text-lb-muted">
              Учись. Развивайся.
              <span className="block text-lb-purple">Побеждай!</span>
            </span>
            <span className="inline-flex size-9 items-center justify-center rounded-xl bg-gradient-to-br from-[#ffd56b] to-lb-gold shadow-[0_4px_12px_-4px_rgba(246,184,47,0.7)]">
              <Trophy className="size-[18px] text-lb-deep" aria-hidden />
            </span>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 pb-10 pt-5 sm:pt-6">
        <Outlet />
      </main>
      <footer className="mx-auto max-w-7xl px-4 pb-8 text-xs text-lb-muted">
        Рейтинг академии OkurmenKIDS. Баллы рассчитываются автоматически по посещаемости, домашним заданиям и тестам;
        изменения в журнале появляются здесь в течение нескольких минут.
      </footer>
    </div>
  )
}
