import '@fontsource-variable/manrope'

import { Suspense, useEffect, useState } from 'react'
import { Menu, X } from 'lucide-react'
import { Link, Outlet, useLocation } from 'react-router-dom'

import logo from '@/assets/logo-careers.png'
import { LoadingState } from '@/components/ui/LoadingState'
import { cn } from '@/utils/cn'

import { COMPANY } from './content'

export const NAV = [
  { hash: 'about', label: 'О нас' },
  { hash: 'culture', label: 'Культура' },
  { hash: 'vacancies', label: 'Вакансии' },
  { hash: 'contact', label: 'Контакты' },
]

export function Logo({ inverse = false }: { inverse?: boolean }) {
  return (
    <Link to="/careers" className="flex min-w-0 items-center gap-3" aria-label={`${COMPANY.name} — карьера, на главную`}>
      <img src={logo} alt="" width={44} height={44} className="size-11 shrink-0" />
      <span className="leading-tight">
        <span className={cn('block font-display text-[15px] font-extrabold tracking-[0.06em]', inverse ? 'text-white' : 'text-ok-indigo')}>{COMPANY.name}</span>
        <span className={cn('block text-xs font-medium', inverse ? 'text-white/70' : 'text-ok-muted')}>Карьера</span>
      </span>
    </Link>
  )
}

/** Карьерный сайт OKURMEN KIDS — публичный, без входа и без навигации LMS;
 * читает только публичный API вакансий. */
export function CareersLayout() {
  const [open, setOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const location = useLocation()
  useEffect(() => setOpen(false), [location.pathname, location.hash])
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <div className="careers-site flex min-h-dvh flex-col bg-ok-paper font-display text-ok-ink">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-white focus:px-3 focus:py-2 focus:text-ok-indigo">
        К содержимому
      </a>
      <header className={cn('sticky top-0 z-40 border-b transition-colors duration-200',
        scrolled || open ? 'border-ok-line bg-ok-paper/95 backdrop-blur' : 'border-transparent bg-ok-paper')}>
        <div className="mx-auto flex h-[72px] max-w-7xl items-center justify-between gap-6 px-5 sm:px-8">
          <Logo />
          <nav aria-label="Разделы сайта" className="hidden items-center gap-8 md:flex">
            {NAV.map((item) => (
              <Link key={item.hash} to={`/careers#${item.hash}`} className="text-[15px] font-semibold text-ok-ink/75 transition-colors hover:text-ok-indigo">
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="flex items-center gap-2">
            <Link to="/careers#vacancies" className="hidden h-11 items-center rounded-full bg-ok-indigo px-5 text-[15px] font-bold text-white transition-colors hover:bg-ok-indigo-soft sm:inline-flex">
              Все вакансии
            </Link>
            <button
              type="button"
              className="flex size-11 items-center justify-center rounded-full text-ok-indigo hover:bg-ok-indigo-50 md:hidden"
              aria-expanded={open}
              aria-controls="careers-mobile-nav"
              aria-label={open ? 'Закрыть меню' : 'Открыть меню'}
              onClick={() => setOpen((v) => !v)}
            >
              {open ? <X className="size-6" aria-hidden /> : <Menu className="size-6" aria-hidden />}
            </button>
          </div>
        </div>
        {open ? (
          <nav id="careers-mobile-nav" aria-label="Разделы сайта" className="border-t border-ok-line px-5 pb-5 pt-2 md:hidden">
            {NAV.map((item) => (
              <Link key={item.hash} to={`/careers#${item.hash}`} className="block border-b border-ok-line py-3.5 text-lg font-semibold text-ok-ink">
                {item.label}
              </Link>
            ))}
            <Link to="/careers#vacancies" className="mt-4 flex h-12 items-center justify-center rounded-full bg-ok-indigo text-base font-bold text-white">
              Все вакансии
            </Link>
          </nav>
        ) : null}
      </header>
      <main id="main" className="flex-1">
        <Suspense fallback={<LoadingState label="Загрузка…" />}>
          <Outlet />
        </Suspense>
      </main>
      <footer className="bg-ok-indigo-deep text-white">
        <div className="mx-auto grid max-w-7xl gap-10 px-5 py-14 sm:px-8 md:grid-cols-[1.4fr_1fr_1fr]">
          <div>
            <Logo inverse />
            <p className="mt-5 max-w-sm text-[15px] leading-relaxed text-white/70">{COMPANY.tagline}. Мы ищем людей, которые хотят делать обучение детей лучше.</p>
          </div>
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-ok-amber">Разделы</p>
            <ul className="mt-4 space-y-2.5 text-[15px]">
              {NAV.map((item) => (
                <li key={item.hash}><Link to={`/careers#${item.hash}`} className="text-white/80 hover:text-white">{item.label}</Link></li>
              ))}
            </ul>
          </div>
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-ok-amber">Кандидатам</p>
            <ul className="mt-4 space-y-2.5 text-[15px]">
              <li><Link to="/careers#vacancies" className="text-white/80 hover:text-white">Открытые вакансии</Link></li>
              <li><Link to="/careers#hiring" className="text-white/80 hover:text-white">Как проходит отбор</Link></li>
              <li><Link to="/careers/privacy" className="text-white/80 hover:text-white">Обработка персональных данных</Link></li>
            </ul>
          </div>
        </div>
        <div className="border-t border-white/10">
          <p className="mx-auto max-w-7xl px-5 py-6 text-sm text-white/55 sm:px-8">© {new Date().getFullYear()} {COMPANY.name}</p>
        </div>
      </footer>
    </div>
  )
}
