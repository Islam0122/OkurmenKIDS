import { useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'

import { t } from '@/i18n'

import { ExamButton } from '../Button/ExamButton'
import { Icon } from '../Icon'
import './Header.css'

const LINKS = [
  { to: '/', label: t.nav.home, icon: 'house', end: true },
  { to: '/training', label: t.nav.training, icon: 'ui-checks-grid' },
  { to: '/leaderboard', label: t.nav.leaderboard, icon: 'trophy' },
  { to: '/videos', label: t.nav.videos, icon: 'camera-video' },
  { to: '/materials', label: t.nav.materials, icon: 'journal-bookmark' },
]

export function Brand() {
  return (
    <NavLink to="/" className="brand" aria-label="Okurmen Kids — башкы бет">
      <img className="brand__logo" src="/logo.png" alt="" width="44" height="44" />
      <span className="brand__text">
        <span className="brand__name">OKURMEN</span>
        <span className="brand__sub">Kids</span>
      </span>
    </NavLink>
  )
}

export function Header() {
  const [open, setOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const location = useLocation()

  useEffect(() => setOpen(false), [location.pathname])
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const links = LINKS.map(({ to, label, icon, end }) => (
    <NavLink key={to} to={to} end={end} className="nav__link">
      <Icon name={icon} />
      {label}
    </NavLink>
  ))

  return (
    <header className={`header${scrolled ? ' is-scrolled' : ''}`}>
      <div className="container header__inner">
        <Brand />
        <nav className="nav" aria-label="Негизги меню">{links}</nav>
        <div className="header__cta"><ExamButton size="sm" /></div>
        <button
          type="button"
          className="burger"
          aria-expanded={open}
          aria-controls="mobile-menu"
          aria-label={t.nav.menu}
          onClick={() => setOpen((v) => !v)}
        >
          <Icon name={open ? 'x-lg' : 'list'} />
        </button>
      </div>
      <div id="mobile-menu" className="drawer" hidden={!open}>
        <nav aria-label="Мобилдик меню">{links}</nav>
        <div className="drawer__cta"><ExamButton block /></div>
      </div>
    </header>
  )
}
