import { AnimatePresence, motion } from 'framer-motion'
import { ChevronDown, Menu, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'

import { NAV } from '@/app/config/site'
import { LanguageSwitcher } from '@/components/navigation/LanguageSwitcher'
import { MobileMenu } from '@/components/navigation/MobileMenu'
import { Logo } from '@/components/shared/Logo'
import { EnrollButton } from '@/features/enrollment/EnrollButton'
import { useI18n } from '@/i18n'
import { cn } from '@/utils/cn'

const linkClass = ({ isActive }: { isActive: boolean }) =>
  cn('relative rounded-full px-2 py-2 text-sm font-semibold whitespace-nowrap transition 2xl:px-3 2xl:text-[15px]', isActive ? 'text-brand-800' : 'text-ink-soft hover:text-brand-800 hover:bg-brand-50/70')

export function Header() {
  const { t, path } = useI18n()
  const [scrolled, setScrolled] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)
  const moreRef = useRef<HTMLDivElement>(null)
  const location = useLocation()

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  useEffect(() => {
    setMenuOpen(false)
    setMoreOpen(false)
  }, [location.pathname])

  useEffect(() => {
    if (!moreOpen) return
    const onClick = (e: MouseEvent) => !moreRef.current?.contains(e.target as Node) && setMoreOpen(false)
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [moreOpen])

  const primary = NAV.filter((item) => item.primary)
  const secondary = NAV.filter((item) => !item.primary && item.path !== '/')

  return (
    <>
      <a href="#main" className="sr-only z-[90] rounded-full bg-gold-400 px-4 py-2 font-bold text-brand-900 focus:not-sr-only focus:fixed focus:top-3 focus:left-3">
        {t('nav.skip')}
      </a>
      <header className={cn('sticky top-0 z-50 transition-all duration-300', scrolled ? 'border-b border-line/80 bg-white/90 shadow-[0_8px_30px_-20px_rgb(41_19_109/0.35)] backdrop-blur-xl' : 'bg-white')}>
        <div className="container-page flex h-[72px] items-center justify-between gap-4 lg:h-20">
          <Logo />
          <nav aria-label={t('nav.menu')} className="hidden items-center gap-0.5 xl:flex">
            {primary.map((item) => (
              <NavLink key={item.path} to={path(item.path)} className={linkClass}>
                {({ isActive }) => (
                  <>
                    {t(item.label)}
                    {isActive ? <motion.span layoutId="nav-underline" className="absolute inset-x-2 -bottom-0.5 h-0.5 rounded-full bg-gold-400" /> : null}
                  </>
                )}
              </NavLink>
            ))}
            <div ref={moreRef} className="relative">
              <button type="button" onClick={() => setMoreOpen((v) => !v)} aria-expanded={moreOpen} aria-haspopup="menu" className="flex items-center gap-1 rounded-full px-2 py-2 text-sm font-semibold whitespace-nowrap 2xl:px-3 2xl:text-[15px] text-ink-soft hover:bg-brand-50/70 hover:text-brand-800">
                {t('nav.more')}
                <ChevronDown className={cn('size-4 transition', moreOpen && 'rotate-180')} aria-hidden />
              </button>
              <AnimatePresence>
                {moreOpen ? (
                  <motion.div role="menu" initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} className="absolute right-0 mt-2 w-60 rounded-2xl border border-line bg-white p-2 shadow-lift">
                    {secondary.map((item) => (
                      <NavLink key={item.path} role="menuitem" to={path(item.path)} className={({ isActive }) => cn('flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold', isActive ? 'bg-brand-50 text-brand-800' : 'text-ink-soft hover:bg-surface-soft')}>
                        <item.icon className="size-4 text-brand-400" aria-hidden />
                        {t(item.label)}
                      </NavLink>
                    ))}
                  </motion.div>
                ) : null}
              </AnimatePresence>
            </div>
          </nav>
          <div className="flex items-center gap-1 sm:gap-2">
            <LanguageSwitcher />
            <div className="hidden sm:block"><EnrollButton size="sm" /></div>
            <button type="button" onClick={() => setMenuOpen(true)} className="grid size-11 place-items-center rounded-full text-brand-800 hover:bg-brand-50 xl:hidden" aria-label={t('nav.menu')} aria-expanded={menuOpen}>
              {menuOpen ? <X className="size-6" aria-hidden /> : <Menu className="size-6" aria-hidden />}
            </button>
          </div>
        </div>
      </header>
      <MobileMenu open={menuOpen} onClose={() => setMenuOpen(false)} />
    </>
  )
}
